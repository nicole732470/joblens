"""Deterministic risk signals (JD visa language, weak resume fit, JD red flags)."""

from __future__ import annotations

from app.schemas.candidate_profile import CandidateProfile
from app.schemas.report import JDParse, ResumeFitAnalysis

_NO_SPONSOR_PHRASES = (
    "no sponsorship",
    "not sponsor",
    "unable to sponsor",
    "will not sponsor",
    "without sponsorship",
    "cannot sponsor",
    "do not sponsor",
    "won't sponsor",
    "not provide visa",
    "must be authorized to work",
    "without employer sponsorship",
)


def _text_denies_sponsorship(text: str) -> bool:
    lower = (text or "").lower()
    return any(p in lower for p in _NO_SPONSOR_PHRASES)


def _jd_sponsorship_veto(jd: JDParse) -> tuple[bool, list[str], str]:
    """Return (veto, jd_evidence_ids, quote)."""
    for req in jd.requirements:
        if req.category == "visa" or _text_denies_sponsorship(req.text):
            if _text_denies_sponsorship(req.text) or req.category == "visa":
                quote = req.evidence_quote or req.text
                if _text_denies_sponsorship(quote) or _text_denies_sponsorship(req.text):
                    return True, [req.id], quote or req.text
    for phrase in jd.visa_language:
        if _text_denies_sponsorship(phrase):
            return True, [], phrase
    return False, [], ""


def run_risk_rules(
    jd: JDParse,
    resume_fit: ResumeFitAnalysis,
    profile: CandidateProfile,
) -> dict:
    """Return RiskAnalysis shape. Never cites h1b evidence."""
    risks: list[dict] = []

    if jd.available and profile.constraints.needs_sponsorship:
        veto, jd_ids, quote = _jd_sponsorship_veto(jd)
        if veto:
            risks.append(
                {
                    "claim": "Job description indicates visa sponsorship may not be available.",
                    "claim_type": "risk",
                    "jd_evidence_ids": jd_ids,
                    "resume_evidence_ids": [],
                    "h1b_evidence_ids": [],
                    "reasoning": f'JD states: "{quote[:200]}"',
                    "inference": False,
                }
            )

    if resume_fit.available:
        missing = len(resume_fit.missing)
        strong = len(resume_fit.strong_matches)
        if missing > 0 and strong == 0 and missing >= 3:
            risks.append(
                {
                    "claim": f"{missing} JD requirements not closely supported on resume.",
                    "claim_type": "risk",
                    "jd_evidence_ids": [
                        c.jd_evidence_ids[0]
                        for c in resume_fit.missing[:3]
                        if c.jd_evidence_ids
                    ],
                    "resume_evidence_ids": [],
                    "h1b_evidence_ids": [],
                    "reasoning": f"{missing} requirement(s) lack strong resume support.",
                    "inference": False,
                }
            )

    if jd.available and jd.risk_keywords:
        sample = jd.risk_keywords[:3]
        risks.append(
            {
                "claim": "Job description contains vague or cautionary language.",
                "claim_type": "risk",
                "jd_evidence_ids": [r.id for r in jd.requirements if r.category == "risk_keyword"][:3],
                "resume_evidence_ids": [],
                "h1b_evidence_ids": [],
                "reasoning": "; ".join(sample),
                "inference": False,
            }
        )

    return {"available": bool(risks), "risks": risks}
