"""Role P-tier adjustments after title track match — JD hardness, not title alone."""

from __future__ import annotations

import re

from app.schemas.candidate_profile import CandidateProfile, Track
from app.schemas.report import JDParse, ResumeFitAnalysis
from app.tools.profile_signals import _anchor_tokens, _jd_scan_blob

# JD signals that the role is a research / PhD-style path (not builder AI).
_RESEARCH_JD_RE = re.compile(
    r"\b("
    r"research scientist|research scientists|research engineering team|"
    r"ph\.?\s*d\.?|doctoral|publications required|publish research|"
    r"frontier ai research"
    r")\b",
    re.I,
)

_SOLUTION_ENG_TITLE_RE = re.compile(
    r"\b(solutions?\s+engineer(?:ing)?|solution\s+architect|forward\s+deployed)\b",
    re.I,
)

# JD signals for customer success / account management (not product or AI engineering).
_CSM_JD_RE = re.compile(
    r"\b("
    r"customer success|voice of the customer|renewal|customer adoption|"
    r"customer lifecycle|success plan|csm\b"
    r")\b",
    re.I,
)


def _strict_phrase_hit(phrase: str, blob_lower: str) -> bool:
    """Require full phrase or all anchor tokens — avoids «engineering» alone matching «mechanical engineering»."""
    p = (phrase or "").strip().lower()
    if not p or not blob_lower:
        return False
    if p in blob_lower:
        return True
    anchors = _anchor_tokens(phrase)
    if not anchors:
        return False
    if len(anchors) == 1:
        return anchors[0] in blob_lower
    return all(a in blob_lower for a in anchors)


def _strict_phrase_hits(phrases: list[str], blob: str) -> tuple[int, list[str]]:
    blob_lower = blob.lower()
    hits = [p for p in phrases if _strict_phrase_hit(p, blob_lower)]
    return len(hits), hits


def apply_technical_penalties(
    track_priority: int | None,
    jd: JDParse,
    jd_text: str,
    profile: CandidateProfile,
) -> tuple[int | None, list[str]]:
    """Bump Role P-tier when JD mentions hard-skill gaps the user listed.

    P1–P2: +1 tier. P3 (e.g. analyst family): +1 → P4 when JD is hardware/HPC-heavy.
    P4+ already: no further bump (Skip rule applies separately).
    """
    if track_priority is None or not profile.technical_penalties:
        return track_priority, []
    if track_priority >= 4:
        return track_priority, []
    blob = _jd_scan_blob(jd, jd_text)
    n, hits = _strict_phrase_hits(profile.technical_penalties, blob)
    if n == 0:
        return track_priority, []
    if track_priority <= 2:
        return min(5, track_priority + 1), hits
    if track_priority == 3:
        return 4, hits
    return track_priority, hits


def _find_track(profile: CandidateProfile, track_id: str) -> Track | None:
    for tr in profile.tracks:
        if tr.id == track_id:
            return tr
    return None


def apply_jd_role_adjustments(
    matched_track: Track | None,
    title: str,
    jd: JDParse,
    jd_text: str,
    profile: CandidateProfile,
) -> tuple[Track | None, int | None, list[str]]:
    """Reconcile title track with JD role family; return track, priority, reasons."""
    if matched_track is None:
        return None, None, []

    blob = _jd_scan_blob(jd, jd_text)
    title_l = (title or "").lower()
    reasons: list[str] = []
    track = matched_track
    priority = track.priority

    # Solution / forward-deployed eng titles stay in product track even when JD
    # mentions collaborating with research or "research problems" in passing.
    if _SOLUTION_ENG_TITLE_RE.search(title_l) and track.id in ("ai_eng", "research_eng", "sde_eng"):
        alt = _find_track(profile, "pm_eng")
        if alt:
            return alt, alt.priority, reasons

    # Title says research but landed on builder AI (embedding drift).
    if track.id == "ai_eng" and (
        "research engineer" in title_l
        or "applied research" in title_l
        or _RESEARCH_JD_RE.search(blob)
    ):
        if not _SOLUTION_ENG_TITLE_RE.search(title_l):
            alt = _find_track(profile, "research_eng")
            if alt:
                track = alt
                priority = alt.priority
                reasons.append("research-path JD")

    # Title or JD is customer success but matched product / AI.
    elif track.id in ("pm_eng", "ai_eng") and (
        "customer success" in title_l or _CSM_JD_RE.search(blob)
    ):
        alt = _find_track(profile, "customer_success")
        if alt:
            track = alt
            priority = alt.priority
            reasons.append("customer success role")

    # Builder AI title + research-heavy JD without research in title.
    elif track.id == "ai_eng" and _RESEARCH_JD_RE.search(blob):
        if not _SOLUTION_ENG_TITLE_RE.search(title_l):
            priority = max(priority, 4)
            reasons.append("research-heavy JD")

    # Analyst title family + HPC/GPU core JD → floor at P4 (triggers Skip).
    elif track.id == "business_analyst":
        n, hits = _strict_phrase_hits(profile.technical_penalties or [], blob)
        if n > 0:
            priority = max(priority, 4)
            reasons.append(f"hardware-heavy JD ({hits[0][:24]})")

    return track, priority, reasons


def _resume_fit_stats(resume_fit: ResumeFitAnalysis) -> tuple[int, int, int, float]:
    strong = len(resume_fit.strong_matches)
    partial = len(resume_fit.partial_matches)
    pure_gap = sum(
        1 for c in resume_fit.missing if not c.resume_evidence_ids
    )
    total = strong + partial + len(resume_fit.missing)
    if total == 0:
        return 0, 0, 0, 0.0
    effective = strong + partial * 0.5
    return strong, pure_gap, total, effective / total


def apply_resume_priority_adjustment(
    track_priority: int | None,
    resume_fit: ResumeFitAnalysis | None,
) -> tuple[int | None, list[str]]:
    """Nudge Role P-tier using resume–JD stack overlap (after title + JD family)."""
    if track_priority is None or resume_fit is None or not resume_fit.available:
        return track_priority, []

    strong, pure_gap, total, ratio = _resume_fit_stats(resume_fit)
    if total == 0:
        return track_priority, []

    reasons: list[str] = []
    priority = track_priority

    if priority <= 2 and ratio < 0.20 and pure_gap >= 2:
        priority = min(5, priority + 1)
        reasons.append(f"low resume overlap ({ratio:.0%})")
    elif priority >= 3 and ratio >= 0.40 and strong >= 2:
        priority = max(1, priority - 1)
        reasons.append(f"strong resume match ({strong}/{total} strong)")

    return priority, reasons
