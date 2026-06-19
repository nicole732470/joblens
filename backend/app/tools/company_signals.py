"""Company fit scoring — employer quality vs profile preferences (NOT H-1B sponsor odds).

Signals: profile preferences, NAICS industry, LinkedIn page text (followers / alumni
lines) sent by the extension from the page the user already has open — no backend
crawler. Startup vs large corp are not opposites; scale does not penalize big companies.
"""

from __future__ import annotations

import re

from app.schemas.candidate_profile import CandidateProfile
from app.schemas.report import JDParse, SponsorshipAnalysis
from app.tools.profile_signals import _dealbreaker_hits, _jd_scan_blob, _semantic_phrase_hits

_TECH_NAICS = frozenset({"51", "54"})
_FINANCE_NAICS = frozenset({"52", "55"})
_TRADITIONAL_NAICS = frozenset({"31", "32", "33", "44", "45", "72"})


def _company_blob(
    company_name: str | None,
    jd: JDParse,
    jd_text: str,
    sponsorship: SponsorshipAnalysis,
    alumni_hints: list[str] | None,
) -> str:
    parts: list[str] = []
    if company_name:
        parts.append(f"Company: {company_name}")
    if sponsorship.matched and sponsorship.company:
        co = sponsorship.company
        if co.name:
            parts.append(co.name)
        if co.naics_sector:
            parts.append(f"Industry: {co.naics_sector}")
        if co.city and co.state:
            parts.append(f"HQ: {co.city}, {co.state}")
    if alumni_hints:
        parts.extend(alumni_hints)
    parts.append(_jd_scan_blob(jd, jd_text))
    blob = " ".join(p for p in parts if p)
    return blob[:4500] if len(blob) > 4500 else blob


def _industry_component(naics_code: str | None, naics_sector: str | None) -> tuple[float, str]:
    code = (naics_code or "").strip()
    sector = (naics_sector or "").strip()
    if not code and not sector:
        return 0.55, "industry unknown"
    prefix = code[:2] if len(code) >= 2 and code[:2].isdigit() else ""
    if prefix in _TECH_NAICS:
        return 0.88, sector or "Information / tech services"
    if prefix in _FINANCE_NAICS:
        return 0.72, sector or "Finance / holding"
    if prefix in _TRADITIONAL_NAICS:
        return 0.48, sector or "Traditional industry"
    return 0.58, sector or "Other industry"


def _followers_component(count: int | None) -> tuple[float, str]:
    """Visibility proxy only — not a startup vs enterprise judgment."""
    if count is None:
        return 0.55, ""
    if count >= 50_000:
        return 0.72, f"{count:,} LinkedIn followers"
    if count >= 5_000:
        return 0.65, f"{count:,} LinkedIn followers"
    return 0.58, f"{count:,} LinkedIn followers"


def _alumni_component(
    profile: CandidateProfile,
    alumni_hints: list[str] | None,
) -> tuple[float, list[str]]:
    schools = profile.alumni_schools or []
    hints = alumni_hints or []
    if not schools or not hints:
        return 0.55, []
    blob = " ".join(hints).lower()
    hits: list[str] = []
    for school in schools:
        s = school.strip().lower()
        if s and s in blob:
            hits.append(school)
    if not hits:
        return 0.55, []
    return 0.55 + 0.15 * min(len(hits), 2), hits


def _preference_component(profile: CandidateProfile, blob: str) -> tuple[float, int, list[str]]:
    total = len(profile.preferences)
    if total == 0:
        return 0.55, 0, []
    n, hits = _semantic_phrase_hits(profile.preferences, blob)
    return 0.35 + 0.65 * (n / total), n, hits


def _score_to_tier(score: float) -> int:
    """Broad bands — most companies land P1 or P2 unless dealbreaker."""
    if score >= 0.52:
        return 1
    if score >= 0.38:
        return 2
    return 3


def score_company(
    company_name: str | None,
    jd: JDParse,
    jd_text: str,
    profile: CandidateProfile,
    sponsorship: SponsorshipAnalysis,
    *,
    linkedin_followers: int | None = None,
    alumni_hints: list[str] | None = None,
) -> dict:
    blob = _company_blob(company_name, jd, jd_text, sponsorship, alumni_hints)
    if not blob.strip():
        return {"available": False, "reason": "no company or JD text"}

    deal_n, deal_hits = _dealbreaker_hits(profile.dealbreakers, blob)
    if deal_n > 0:
        hit = deal_hits[0][:48]
        return {
            "available": True,
            "company_score": 0.25,
            "company_tier": 3,
            "company_label": f"P3 · dealbreaker ({hit})",
            "summary": f"Company/JD hits dealbreaker: {hit}",
            "preference_hits": [],
            "industry_label": None,
            "dealbreakers_matched": deal_n,
            "dealbreaker_hits": deal_hits[:5],
            "score_breakdown": {"reason": "dealbreaker", "hit": hit},
            "linkedin_followers": linkedin_followers,
            "alumni_hits": [],
        }

    pref_score, pref_n, pref_hits = _preference_component(profile, blob)
    naics_code = sponsorship.company.naics_code if sponsorship.company else None
    naics_sector = sponsorship.company.naics_sector if sponsorship.company else None
    ind_score, ind_label = _industry_component(naics_code, naics_sector)
    fol_score, fol_label = _followers_component(linkedin_followers)
    alum_score, alum_hits = _alumni_component(profile, alumni_hints)

    combined = 0.50 * pref_score + 0.28 * ind_score + 0.12 * fol_score + 0.10 * alum_score
    if pref_n >= 2:
        combined = min(1.0, combined + 0.08)
    elif pref_n >= 1:
        combined = min(1.0, combined + 0.04)

    tier = _score_to_tier(combined)

    parts: list[str] = [f"P{tier}"]
    if pref_hits:
        parts.append(pref_hits[0][:28])
    elif alum_hits:
        parts.append(f"{alum_hits[0][:20]} alumni")
    elif ind_label != "industry unknown":
        parts.append(ind_label[:28])

    summary_bits: list[str] = []
    if fol_label:
        summary_bits.append(fol_label)
    if alum_hits:
        summary_bits.append(f"{', '.join(alum_hits[:2])} alumni on LinkedIn")
    if pref_hits:
        summary_bits.append(f"{pref_n} preference hit(s)")
    elif ind_label and ind_label != "industry unknown":
        summary_bits.append(ind_label)

    return {
        "available": True,
        "company_score": round(combined, 3),
        "company_tier": tier,
        "company_label": " · ".join(parts[:2]),
        "summary": " · ".join(summary_bits[:3]) or f"Company fit {combined:.0%}",
        "preference_hits": pref_hits[:5],
        "industry_label": ind_label if ind_label != "industry unknown" else None,
        "dealbreakers_matched": 0,
        "dealbreaker_hits": [],
        "score_breakdown": {
            "preference": round(pref_score, 3),
            "industry": round(ind_score, 3),
            "followers": round(fol_score, 3),
            "alumni": round(alum_score, 3),
            "combined": round(combined, 3),
            "weights": "50% pref · 28% industry · 12% followers · 10% alumni",
        },
        "linkedin_followers": linkedin_followers,
        "alumni_hits": alum_hits[:5],
    }


# Technical penalty logic lives in role_priority.py (Role P-tier, not company score).
