"""Apply / skip recommendation from profile + JD + resume fit (never H-1B DB)."""

from __future__ import annotations

from app.schemas.candidate_profile import CandidateProfile, Track
from app.schemas.report import JDParse, Recommendation, ResumeFitAnalysis
from app.tools.risk_rules import _jd_sponsorship_veto
from app.tools.track_match import match_title_to_profile


def _fit_counts(resume_fit: ResumeFitAnalysis) -> tuple[int, int, int, int, float]:
    """Return strong, partial, weak, pure_gap, effective_ratio."""
    strong = len(resume_fit.strong_matches)
    partial = len(resume_fit.partial_matches)
    weak = sum(1 for c in resume_fit.missing if c.resume_evidence_ids)
    pure_gap = len(resume_fit.missing) - weak
    total = strong + partial + len(resume_fit.missing)
    if total == 0:
        return 0, 0, 0, 0, 0.0
    effective = strong + partial + weak * 0.65
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


def generate_recommendation(
    jd: JDParse,
    resume_fit: ResumeFitAnalysis,
    profile: CandidateProfile,
    job_title: str | None,
) -> dict:
    """Return RecommendationResult shape. Does not use H-1B database signals."""
    title = job_title or ""

    if not jd.available:
        return {"available": False, "reason": "JD parsing unavailable"}

    if profile.constraints.needs_sponsorship:
        veto, jd_ids, quote = _jd_sponsorship_veto(jd)
        if veto:
            return {
                "available": True,
                "decision": Recommendation.SKIP,
                "reasoning": f'Job posting states no sponsorship: "{quote[:180]}"',
                "evidence_ids": [e for e in jd_ids if e],
            }

    tm = match_title_to_profile(title, profile)
    track: Track | None = tm["matched_track"]
    track_sim: float = tm["similarity"]

    if tm["avoid_match"]:
        return {
            "available": True,
            "decision": Recommendation.SKIP,
            "reasoning": f"Title semantically matches your avoid track ({tm['avoid_label']}).",
            "evidence_ids": [],
            "track_id": track.id if track else None,
            "track_label": track.label if track else None,
            "track_priority": track.priority if track else None,
            "track_similarity": track_sim,
        }

    if not resume_fit.available:
        return {
            "available": False,
            "reason": resume_fit.reason or "resume fit unavailable",
            "track_id": track.id if track else None,
            "track_label": track.label if track else None,
            "track_priority": track.priority if track else None,
            "track_similarity": track_sim,
        }

    strong, partial, weak, pure_gap, ratio = _fit_counts(resume_fit)
    total = strong + partial + weak + pure_gap
    if total == 0:
        return {"available": False, "reason": "no requirements to score against resume"}

    track_note = ""
    if track:
        track_note = (
            f" Role matches your «{track.label}» track (priority {track.priority}, "
            f"similarity {track_sim:.0%})."
        )

    # Priority 1–2 target roles: default to at least «apply with modifications», not Skip.
    priority_floor = track is not None and track.priority <= 2 and track_sim >= 0.30

    if strong >= max(2, total * 0.3) and ratio >= 0.48:
        decision = Recommendation.APPLY
        reasoning = (
            f"{strong} strong, {partial} partial, {weak} weak across {total} JD requirements "
            f"(vector fit ratio {ratio:.0%}).{track_note}"
        )
    elif ratio >= 0.35 or (partial + weak) >= max(2, total * 0.3):
        decision = Recommendation.APPLY_WITH_MODIFICATIONS
        reasoning = (
            f"Resume touches {strong + partial + weak}/{total} requirements "
            f"(fit ratio {ratio:.0%}); {pure_gap} clear gap(s).{track_note}"
        )
    elif ratio >= 0.15 or priority_floor:
        decision = Recommendation.LOW_PRIORITY if not priority_floor else Recommendation.APPLY_WITH_MODIFICATIONS
        reasoning = (
            f"Limited vector overlap ({ratio:.0%}) but role fits your profile.{track_note}"
            if priority_floor
            else f"Limited overlap ({ratio:.0%}).{track_note}"
        )
    else:
        decision = Recommendation.SKIP
        reasoning = f"Low resume–JD vector overlap ({ratio:.0%}).{track_note}"

    if priority_floor and decision == Recommendation.SKIP:
        decision = Recommendation.APPLY_WITH_MODIFICATIONS
        reasoning += " Priority 1–2 track match — not skipping on title fit alone."

    if (
        track
        and track.priority <= 2
        and decision == Recommendation.LOW_PRIORITY
        and (_jd_mentions_ai(jd) or ratio >= 0.12)
    ):
        decision = Recommendation.APPLY_WITH_MODIFICATIONS
        reasoning += " Bumped: priority target + relevant AI/agent JD."

    return {
        "available": True,
        "decision": decision,
        "reasoning": reasoning.strip(),
        "evidence_ids": _collect_evidence_ids(resume_fit, jd),
        "track_id": track.id if track else None,
        "track_label": track.label if track else None,
        "track_priority": track.priority if track else None,
        "track_similarity": track_sim,
        "fit_ratio": round(ratio, 3),
    }
