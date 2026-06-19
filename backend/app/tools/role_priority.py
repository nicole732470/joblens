"""Role P-tier adjustments after title track match — JD hardness, not title alone."""

from __future__ import annotations

import re

from app.schemas.candidate_profile import CandidateProfile, Track
from app.schemas.report import JDParse
from app.tools.profile_signals import _anchor_tokens, _jd_scan_blob

# JD signals that the role is a research / PhD-style path (not builder AI).
_RESEARCH_JD_RE = re.compile(
    r"\b("
    r"research scientist|research scientists|research engineering team|"
    r"research breakthroughs|alongside research|ph\.?\s*d\.?|doctoral|"
    r"publications|frontier ai research|embed in our ai team"
    r")\b",
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

    Only applies when the title pulled a strong track (P1–P2) — analyst/HPC-style
    roles already sit at P3+ and should not get an extra +1.
    """
    if track_priority is None or track_priority > 2 or not profile.technical_penalties:
        return track_priority, []
    blob = _jd_scan_blob(jd, jd_text)
    n, hits = _strict_phrase_hits(profile.technical_penalties, blob)
    if n == 0:
        return track_priority, []
    return min(5, track_priority + 1), hits


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

    # Title says research but landed on builder AI (embedding drift).
    if track.id == "ai_eng" and (
        "research engineer" in title_l
        or "applied research" in title_l
        or _RESEARCH_JD_RE.search(blob)
    ):
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
        priority = max(priority, 4)
        reasons.append("research-heavy JD")

    # Analyst title family + HPC/GPU core JD — floor at P4 without extra penalty stack.
    elif track.id == "business_analyst" and priority >= 4:
        n, hits = _strict_phrase_hits(profile.technical_penalties or [], blob)
        if n > 0:
            priority = max(priority, 4)
            reasons.append(f"hardware-heavy JD ({hits[0][:24]})")

    return track, priority, reasons
