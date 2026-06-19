"""Apply / skip recommendation from profile + JD + resume fit (never H-1B DB)."""

from __future__ import annotations

from app.schemas.candidate_profile import CandidateProfile, Track
from app.schemas.report import JDParse, Recommendation, ResumeFitAnalysis
from app.tools.risk_rules import _jd_sponsorship_veto


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


def _best_track(title: str, profile: CandidateProfile) -> Track | None:
    hits = [tr for tr in profile.tracks if _title_hits_track(title, tr)]
    if not hits:
        return None
    return min(hits, key=lambda tr: tr.priority)


def _avoid_track_hit(title: str, profile: CandidateProfile) -> bool:
    t = (title or "").lower()
    for avoid in profile.avoid_tracks:
        if _title_hits_track(title, avoid):
            return True
        if avoid.label.lower() in t:
            return True
    return False


def _collect_evidence_ids(resume_fit: ResumeFitAnalysis, jd: JDParse) -> list[str]:
    ids: list[str] = []
    for bucket in (resume_fit.strong_matches, resume_fit.partial_matches, resume_fit.missing):
        for claim in bucket:
            ids.extend(claim.jd_evidence_ids)
            ids.extend(claim.resume_evidence_ids)
    ids.extend(jd.evidence_ids or [])
    # De-dupe, preserve order.
    seen: set[str] = set()
    out: list[str] = []
    for eid in ids:
        if eid and eid not in seen:
            seen.add(eid)
            out.append(eid)
    return out


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

    strong = len(resume_fit.strong_matches)
    partial = len(resume_fit.partial_matches)
    missing = len(resume_fit.missing)
    total = strong + partial + missing
    if total == 0:
        return {"available": False, "reason": "no requirements to score against resume"}

    supported = strong + partial
    ratio = supported / total
    track = _best_track(title, profile)
    track_note = f" Best-fit track: {track.label} (priority {track.priority})." if track else ""

    if strong >= max(2, total * 0.35) and ratio >= 0.55:
        decision = Recommendation.APPLY
        reasoning = f"{strong} strong and {partial} partial matches out of {total} requirements.{track_note}"
    elif ratio >= 0.45:
        decision = Recommendation.APPLY_WITH_MODIFICATIONS
        reasoning = (
            f"Decent overlap ({supported}/{total} requirements supported) but "
            f"{missing} gap(s) remain — consider tailoring resume.{track_note}"
        )
    elif ratio >= 0.2:
        decision = Recommendation.LOW_PRIORITY
        reasoning = (
            f"Limited overlap ({supported}/{total}). Worth a look only if the role "
            f"fits your target tracks.{track_note}"
        )
    else:
        decision = Recommendation.SKIP
        reasoning = f"Resume supports few requirements ({supported}/{total}).{track_note}"

    # Priority-1 track gets a small bump from Low priority to Apply with modifications.
    if track and track.priority == 1 and decision == Recommendation.LOW_PRIORITY and ratio >= 0.3:
        decision = Recommendation.APPLY_WITH_MODIFICATIONS
        reasoning += " Bumped: priority-1 target role with partial overlap."

    return {
        "available": True,
        "decision": decision,
        "reasoning": reasoning.strip(),
        "evidence_ids": _collect_evidence_ids(resume_fit, jd),
    }
