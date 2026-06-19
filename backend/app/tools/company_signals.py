"""Company fit scoring — employer quality vs profile preferences (NOT H-1B sponsor odds).

Uses JD company description, profile preferences/dealbreakers, and public employer
metadata (NAICS industry, filing volume as scale proxy). Does not treat «has LCA
history» as a positive recommendation factor (see docs/FIT_AND_RECOMMENDATION §6).

Weight scheme (v0 — tune with golden set; discuss before changing):
  preference hits (incl. stack / VC / industry prefs) … 45%
  NAICS industry band                         … 30%
  employer scale vs startup prefs             … 15%
  dealbreaker on company/JD blob              … forces P3
"""

from __future__ import annotations

from app.schemas.candidate_profile import CandidateProfile
from app.schemas.report import JDParse, SponsorshipAnalysis
from app.tools.profile_signals import _jd_scan_blob, _semantic_phrase_hits

# NAICS 2-digit prefixes — coarse industry band (from DOL employer index).
_TECH_NAICS = frozenset({"51", "54"})
_FINANCE_NAICS = frozenset({"52", "55"})
_TRADITIONAL_NAICS = frozenset({"31", "32", "33", "44", "45", "72"})

_STARTUP_PREF_TOKENS = ("startup", "pre-ipo", "pre ipo", "y combinator", "yc ", "a16z", "vc backed")
_LARGE_CORP_LCA = 2_500
_SMALL_EMPLOYER_LCA = 80

_STARTUP_JD_KW = (
    "startup",
    "early-stage",
    "early stage",
    "seed round",
    "series a",
    "backed by a16z",
    "a16z ",
    "y combinator",
    "pre-ipo",
)


def _jd_startup_signal(blob: str) -> bool:
    b = blob.lower()
    return any(k in b for k in _STARTUP_JD_KW)


def _company_blob(
    company_name: str | None,
    jd: JDParse,
    jd_text: str,
    sponsorship: SponsorshipAnalysis,
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
        return 0.92, sector or "Information / tech services"
    if prefix in _FINANCE_NAICS:
        return 0.72, sector or "Finance / holding"
    if prefix in _TRADITIONAL_NAICS:
        return 0.38, sector or "Traditional industry"
    label = sector or "Other industry"
    return 0.58, label


def _scale_component(lca_count: int, pref_blob: str, jd_blob: str) -> tuple[float, str]:
    """Scale proxy from historical LCA volume — not sponsorship quality."""
    wants_startup = any(t in pref_blob for t in _STARTUP_PREF_TOKENS) or _jd_startup_signal(jd_blob)
    if lca_count <= 0:
        if _jd_startup_signal(jd_blob):
            return 0.82, "startup signals in JD"
        return 0.55, "scale unknown"
    if wants_startup:
        if lca_count >= _LARGE_CORP_LCA:
            return 0.32, f"large employer ({lca_count:,} filings)"
        if lca_count <= _SMALL_EMPLOYER_LCA:
            return 0.88, f"small employer ({lca_count:,} filings)"
        return 0.62, f"mid-size ({lca_count:,} filings)"
    if lca_count >= _LARGE_CORP_LCA:
        return 0.68, f"enterprise ({lca_count:,} filings)"
    if lca_count <= _SMALL_EMPLOYER_LCA:
        return 0.52, f"small ({lca_count:,} filings)"
    return 0.6, f"mid-size ({lca_count:,} filings)"


def _preference_component(
    profile: CandidateProfile,
    blob: str,
) -> tuple[float, int, list[str]]:
    total = len(profile.preferences)
    if total == 0:
        return 0.55, 0, []
    n, hits = _semantic_phrase_hits(profile.preferences, blob)
    ratio = n / total
    score = 0.35 + 0.65 * ratio
    return score, n, hits


def _score_to_tier(score: float) -> int:
    if score >= 0.68:
        return 1
    if score >= 0.42:
        return 2
    return 3


def score_company(
    company_name: str | None,
    jd: JDParse,
    jd_text: str,
    profile: CandidateProfile,
    sponsorship: SponsorshipAnalysis,
) -> dict:
    """Return CompanyAnalysis-shaped dict."""
    blob = _company_blob(company_name, jd, jd_text, sponsorship)
    if not blob.strip():
        return {"available": False, "reason": "no company or JD text"}

    deal_n, deal_hits = _semantic_phrase_hits(profile.dealbreakers, blob)
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
        }

    pref_score, pref_n, pref_hits = _preference_component(profile, blob)
    naics_code = sponsorship.company.naics_code if sponsorship.company else None
    naics_sector = sponsorship.company.naics_sector if sponsorship.company else None
    ind_score, ind_label = _industry_component(naics_code, naics_sector)

    lca_count = sponsorship.total_lca_count if sponsorship.matched else 0
    pref_blob = " ".join(profile.preferences).lower()
    scale_score, scale_label = _scale_component(lca_count, pref_blob, blob)

    combined = 0.45 * pref_score + 0.30 * ind_score + 0.15 * scale_score + 0.10 * 0.55
    if pref_n >= 2:
        combined = min(1.0, combined + 0.12)
    elif pref_n >= 1 and (_jd_startup_signal(blob) or ind_score >= 0.9):
        combined = min(1.0, combined + 0.08)
    if wants_startup := any(t in pref_blob for t in _STARTUP_PREF_TOKENS):
        if lca_count >= _LARGE_CORP_LCA:
            combined = max(0.2, combined - 0.12)
        elif lca_count <= _SMALL_EMPLOYER_LCA or _jd_startup_signal(blob):
            combined = min(1.0, combined + 0.06)

    tier = _score_to_tier(combined)

    parts: list[str] = [f"P{tier}"]
    if pref_hits:
        parts.append(pref_hits[0][:32])
    elif ind_label:
        parts.append(ind_label[:32])
    else:
        parts.append(scale_label[:32])

    summary_bits: list[str] = []
    if pref_hits:
        summary_bits.append(f"{pref_n} preference hit(s)")
    if ind_label and ind_label != "industry unknown":
        summary_bits.append(ind_label)
    if sponsorship.matched and scale_label:
        summary_bits.append(scale_label)

    return {
        "available": True,
        "company_score": round(combined, 3),
        "company_tier": tier,
        "company_label": " · ".join(parts[:2]),
        "summary": " · ".join(summary_bits[:3]) or f"Company fit score {combined:.0%}",
        "preference_hits": pref_hits[:5],
        "industry_label": ind_label if ind_label != "industry unknown" else None,
        "dealbreakers_matched": 0,
    }
