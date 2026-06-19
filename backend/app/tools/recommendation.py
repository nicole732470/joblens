"""Apply / skip recommendation from profile + JD + resume fit (never H-1B DB)."""

from __future__ import annotations

from app.schemas.candidate_profile import CandidateProfile, Track
from app.schemas.report import JDParse, Recommendation, ResumeFitAnalysis
from app.tools.risk_rules import _jd_sponsorship_veto

# Title hints when profile example_titles don't list a variant (e.g. "Member of Technical Staff").
_AI_TITLE_HINTS = (
    "technical staff",
    "member of technical staff",
    "research engineer",
    "applied research",
    "ml engineer",
    "ai engineer",
    "software engineer",
    "staff engineer",
    "founding engineer",
)


def _title_tokens(title: str) -> set[str]:
    return {w.lower() for w in title.replace("/", " ").replace("-", " ").split() if len(w) > 2}


def _title_hits_track(title: str, track: Track) -> bool:
    t = (title or "").lower()
    if not t:
        return False
    needles = [track.label, *track.example_titles]
    for needle in needles:
        n = (needle or "").lower().strip()
        if not n:
            continue
        if n in t or t in n:
            return True
        if _title_tokens(t) & _title_tokens(n):
            return True
    return False


def _title_looks_ai_engineering(title: str) -> bool:
    t = (title or "").lower()
    return any(h in t for h in _AI_TITLE_HINTS)


def _best_track(title: str, profile: CandidateProfile) -> Track | None:
    hits = [tr for tr in profile.tracks if _title_hits_track(title, tr)]
    if hits:
        return min(hits, key=lambda tr: tr.priority)
    if _title_looks_ai_engineering(title):
        ai_tracks = [tr for tr in profile.tracks if tr.id == "ai_eng" or "ai" in tr.label.lower()]
        if ai_tracks:
            return min(ai_tracks, key=lambda tr: tr.priority)
    return None


def _avoid_track_hit(title: str, profile: CandidateProfile) -> bool:
    for avoid in profile.avoid_tracks:
        if _title_hits_track(title, avoid):
            return True
        if avoid.label.lower() in (title or "").lower():
            return True
    return False


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

    if _avoid_track_hit(title, profile):
        return {
            "available": True,
            "decision": Recommendation.SKIP,
            "reasoning": "Role type matches your avoid list in candidate profile.",
            "evidence_ids": [],
        }

    if not resume_fit.available:
        return {
            "available": False,
            "reason": resume_fit.reason or "resume fit unavailable",
        }

    strong, partial, weak, pure_gap, ratio = _fit_counts(resume_fit)
    total = strong + partial + weak + pure_gap
    if total == 0:
        return {"available": False, "reason": "no requirements to score against resume"}

    track = _best_track(title, profile)
    track_note = f" Target track: {track.label} (priority {track.priority})." if track else ""

    if strong >= max(2, total * 0.3) and ratio >= 0.5:
        decision = Recommendation.APPLY
        reasoning = (
            f"{strong} strong, {partial} partial, {weak} weak overlap "
            f"across {total} requirements.{track_note}"
        )
    elif ratio >= 0.38 or (partial + weak) >= max(2, total * 0.35):
        decision = Recommendation.APPLY_WITH_MODIFICATIONS
        reasoning = (
            f"Good role fit ({partial + weak + strong}/{total} requirements touched); "
            f"{pure_gap} clear gap(s) — tailor resume.{track_note}"
        )
    elif ratio >= 0.18:
        decision = Recommendation.LOW_PRIORITY
        reasoning = (
            f"Limited resume overlap ({strong + partial + weak}/{total}). "
            f"Consider if the track/location match your goals.{track_note}"
        )
    else:
        decision = Recommendation.SKIP
        reasoning = f"Resume overlap too low ({strong + partial + weak}/{total}).{track_note}"

    # Priority-1 target role + AI JD → don't Skip when there's any signal.
    if (
        track
        and track.priority <= 2
        and decision in (Recommendation.SKIP, Recommendation.LOW_PRIORITY)
        and (ratio >= 0.12 or weak + partial >= 2 or _jd_mentions_ai(jd))
    ):
        decision = Recommendation.APPLY_WITH_MODIFICATIONS
        reasoning += " Bumped: priority target role with relevant AI/agent JD."

    return {
        "available": True,
        "decision": decision,
        "reasoning": reasoning.strip(),
        "evidence_ids": _collect_evidence_ids(resume_fit, jd),
    }
