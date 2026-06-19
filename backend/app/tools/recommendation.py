"""Apply / skip recommendation from profile + JD + resume fit (never H-1B DB)."""

from __future__ import annotations

from app.schemas.candidate_profile import CandidateProfile, Track
from app.schemas.report import JDParse, Recommendation, ResumeFitAnalysis
from app.tools.profile_signals import evaluate_profile_signals
from app.tools.risk_rules import _jd_sponsorship_veto
from app.tools.role_priority import apply_jd_role_adjustments, apply_technical_penalties
from app.tools.track_match import match_job_to_profile, resolve_job_title


# Resume–requirement match weights (tune via golden set / run_eval).
_PARTIAL_WEIGHT = 0.5
_WEAK_WEIGHT = 0.3


def _fit_counts(resume_fit: ResumeFitAnalysis) -> tuple[int, int, int, int, float]:
    """Return strong, partial, weak, pure_gap, effective_ratio."""
    strong = len(resume_fit.strong_matches)
    partial = len(resume_fit.partial_matches)
    weak = sum(1 for c in resume_fit.missing if c.resume_evidence_ids)
    pure_gap = len(resume_fit.missing) - weak
    total = strong + partial + len(resume_fit.missing)
    if total == 0:
        return 0, 0, 0, 0, 0.0
    effective = strong + partial * _PARTIAL_WEIGHT + weak * _WEAK_WEIGHT
    return strong, partial, weak, pure_gap, effective / total


def _collect_evidence_ids(resume_fit: ResumeFitAnalysis, jd: JDParse) -> list[str]:
    ids: list[str] = []
    for bucket in (resume_fit.strong_matches, resume_fit.partial_matches, resume_fit.missing):
        for claim in bucket:
            ids.extend(claim.jd_evidence_ids)
            ids.extend(claim.resume_evidence_ids)
    ids.extend(jd.evidence_ids or [])
    seen: set[str] = set()
    out: list[str] = []
    for eid in ids:
        if eid and eid not in seen:
            seen.add(eid)
            out.append(eid)
    return out


def _jd_mentions_ai(jd: JDParse) -> bool:
    blob = " ".join(
        [*(r.text for r in jd.requirements), *(jd.visa_language or []), *(jd.risk_keywords or [])]
    ).lower()
    return any(k in blob for k in ("llm", "agent", "rag", "generative ai", "machine learning", "ai "))


def _build_summary(
    decision: Recommendation,
    track: Track | None,
    ratio: float,
    strong: int,
    partial: int,
    pure_gap: int,
    signals: dict,
    *,
    dealbreaker_hits: list[str] | None = None,
    avoid_label: str | None = None,
    technical_penalty_hits: list[str] | None = None,
) -> str:
    """One short UI line — not a gap count."""
    if decision == Recommendation.SKIP:
        if dealbreaker_hits:
            return f"Dealbreaker: {dealbreaker_hits[0][:40]}"
        if avoid_label:
            return f"Avoid track ({avoid_label})"
        if ratio < 0.15:
            return "Low resume overlap"
        return "Not a strong fit"

    parts: list[str] = []
    if track:
        parts.append(track.label)

    if technical_penalty_hits:
        parts.append(f"technical gap ({technical_penalty_hits[0][:28]})")

    if ratio >= 0.48 and strong >= 2:
        parts.append("strong skill match")
    elif ratio >= 0.35 or partial >= 2:
        parts.append("partial skill match")
    elif pure_gap > strong + partial:
        parts.append("key skills missing")
    elif ratio < 0.2:
        parts.append("limited resume overlap")
    else:
        parts.append("mixed fit")

    loc_tier = signals.get("location_tier")
    loc_label = signals.get("location_label") or ""
    if loc_tier == 3:
        place = loc_label.split("·", 1)[-1].strip() if "·" in loc_label else ""
        parts.append(f"location P3{f' ({place})' if place and place not in ('unspecified', 'onsite') else ''}")
    elif loc_tier == 1:
        parts.append("preferred location")

    return " · ".join(parts[:3])


def _signal_fields(signals: dict) -> dict:
    return {k: signals[k] for k in (
        "location_score", "location_label", "location_tier",
        "preferences_matched", "preferences_total",
        "dealbreakers_matched", "dealbreakers_total",
    )}


def _apply_track_penalties(
    track_fields: dict,
    title: str,
    jd: JDParse,
    jd_text: str,
    profile: CandidateProfile,
) -> dict:
    track_id = track_fields.get("track_id")
    matched: Track | None = None
    if track_id:
        for tr in profile.tracks:
            if tr.id == track_id:
                matched = tr
                break

    adjusted_track, priority, jd_reasons = apply_jd_role_adjustments(
        matched, title, jd, jd_text, profile
    )
    if adjusted_track:
        track_fields = {
            **track_fields,
            "track_id": adjusted_track.id,
            "track_label": adjusted_track.label,
            "track_priority": priority,
        }

    pen_priority, hits = apply_technical_penalties(
        track_fields.get("track_priority"), jd, jd_text, profile
    )
    return {
        **track_fields,
        "track_priority": pen_priority,
        "technical_penalty_hits": hits + jd_reasons,
    }


def _resolve_display_track(
    track_fields: dict,
    profile: CandidateProfile,
    fallback: Track | None,
) -> Track | None:
    tid = track_fields.get("track_id")
    if tid:
        for tr in profile.tracks:
            if tr.id == tid:
                return tr
    return fallback


def generate_recommendation(
    jd: JDParse,
    resume_fit: ResumeFitAnalysis,
    profile: CandidateProfile,
    job_title: str | None,
    jd_text: str | None = None,
) -> dict:
    """Return RecommendationResult shape. Does not use H-1B database signals."""
    title = resolve_job_title(job_title, jd_text)
    raw_jd = jd_text or ""

    signals = evaluate_profile_signals(jd, raw_jd, profile, title)
    tm = match_job_to_profile(title, raw_jd, jd, profile)
    track: Track | None = tm["matched_track"]
    track_sim: float = tm["similarity"]
    track_fields = _apply_track_penalties(
        {
            "track_id": track.id if track else None,
            "track_label": track.label if track else None,
            "track_priority": track.priority if track else None,
            "track_similarity": track_sim,
        },
        title,
        jd,
        raw_jd,
        profile,
    )

    display_track = _resolve_display_track(track_fields, profile, track)

    if signals["dealbreakers_matched"] > 0:
        hits = signals.get("dealbreaker_hits") or []
        return {
            "available": True,
            "decision": Recommendation.SKIP,
            "reasoning": f"JD hits your dealbreaker(s): {', '.join(hits)[:120]}",
            "summary": _build_summary(
                Recommendation.SKIP, None, 0.0, 0, 0, 0, signals, dealbreaker_hits=hits
            ),
            "evidence_ids": [],
            "fit_ratio": None,
            **_signal_fields(signals),
            **track_fields,
        }

    if not jd.available:
        return {"available": False, "reason": "JD parsing unavailable"}

    if profile.constraints.needs_sponsorship:
        veto, jd_ids, quote = _jd_sponsorship_veto(jd)
        if veto:
            return {
                "available": True,
                "decision": Recommendation.SKIP,
                "reasoning": f'Job posting states no sponsorship: "{quote[:180]}"',
                "summary": "No visa sponsorship stated",
                "evidence_ids": [e for e in jd_ids if e],
                **_signal_fields(signals),
                **track_fields,
            }

    if tm["avoid_match"]:
        return {
            "available": True,
            "decision": Recommendation.SKIP,
            "reasoning": f"Title semantically matches your avoid track ({tm['avoid_label']}).",
            "summary": _build_summary(
                Recommendation.SKIP, display_track, 0.0, 0, 0, 0, signals, avoid_label=tm["avoid_label"]
            ),
            "evidence_ids": [],
            **_signal_fields(signals),
            **track_fields,
        }

    if not resume_fit.available:
        return {
            "available": False,
            "reason": resume_fit.reason or "resume fit unavailable",
            **_signal_fields(signals),
            **track_fields,
        }

    strong, partial, weak, pure_gap, ratio = _fit_counts(resume_fit)
    total = strong + partial + weak + pure_gap
    if total == 0:
        return {"available": False, "reason": "no requirements to score against resume"}

    track_note = ""
    penalized_priority = track_fields.get("track_priority")
    if display_track:
        track_note = (
            f" Role content matches your «{display_track.label}» track (priority {penalized_priority}, "
            f"similarity {track_sim:.0%})."
        )

    signal_fields = _signal_fields(signals)

    # P1–P2 title match: floor at Consider, not Skip (title fit alone is not Apply).
    priority_floor = (
        display_track is not None
        and penalized_priority is not None
        and penalized_priority <= 2
        and track_sim >= 0.30
        and not track_fields.get("technical_penalty_hits")
    )

    if strong >= 2 and ratio >= 0.50:
        decision = Recommendation.APPLY
        reasoning = (
            f"{strong} strong, {partial} partial, {weak} weak across {total} JD requirements "
            f"(vector fit ratio {ratio:.0%}).{track_note}"
        )
    elif ratio >= 0.28 or (partial + weak) >= max(2, total * 0.25):
        decision = Recommendation.CONSIDER
        reasoning = (
            f"Resume touches {strong + partial + weak}/{total} requirements "
            f"(fit ratio {ratio:.0%}); {pure_gap} clear gap(s).{track_note}"
        )
    elif priority_floor and ratio >= 0.12:
        decision = Recommendation.CONSIDER
        reasoning = f"Limited overlap ({ratio:.0%}) but role fits your target track.{track_note}"
    elif ratio >= 0.12:
        decision = Recommendation.CONSIDER
        reasoning = f"Limited overlap ({ratio:.0%}).{track_note}"
    else:
        decision = Recommendation.SKIP
        reasoning = f"Low resume–JD vector overlap ({ratio:.0%}).{track_note}"

    if priority_floor and decision == Recommendation.SKIP:
        decision = Recommendation.CONSIDER
        reasoning += " Priority 1–2 track match — not skipping on title fit alone."

    return {
        "available": True,
        "decision": decision,
        "reasoning": reasoning.strip(),
        "summary": _build_summary(decision, display_track, ratio, strong, partial, pure_gap, signals,
                                  technical_penalty_hits=track_fields.get("technical_penalty_hits")),
        "evidence_ids": _collect_evidence_ids(resume_fit, jd),
        "fit_ratio": round(ratio, 3),
        **signal_fields,
        **track_fields,
    }
