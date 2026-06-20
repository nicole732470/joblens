"""Deterministic analyze pipeline steps — store artifacts + trace tool calls."""

from __future__ import annotations

from app.config import settings
from app.schemas.report import JDParse, ResumeFitAnalysis, SponsorshipAnalysis
from app.tools.analysis_context import get_artifact, get_input, record_tool_call, set_artifact
from app.tools.company_signals import score_company
from app.tools.jd_parser import parse_job_description
from app.tools.llm import llm_available
from app.tools.profile_loader import get_candidate_profile
from app.tools.recommendation import generate_recommendation
from app.tools.resume_fit import analyze_resume_fit
from app.tools.risk_rules import run_risk_rules
from app.tools.sponsorship import search_h1b_company


def _store(name: str, result: dict, *, args: dict | None = None) -> dict:
    set_artifact(name, result)
    record_tool_call(name, args=args, ok=bool(result.get("available", True)))
    return result


def _cached_artifact(artifact_key: str) -> dict:
    cached = get_artifact(artifact_key)
    return cached if isinstance(cached, dict) else {}


def lookup_h1b_sponsorship(company: str) -> dict:
    """Look up H-1B/LCA filing history for an employer."""
    result = search_h1b_company(company)
    return _store("sponsorship", result, args={"company": company})


def parse_jd_structured(jd_text: str, title: str = "") -> dict:
    """Extract structured requirements, location, visa language from a JD."""
    result = parse_job_description(jd_text, title or None)
    return _store("jd", result, args={"title": title})


def score_resume_against_jd(resume_text: str) -> dict:
    """RAG retrieval + LLM classification of resume vs each JD requirement."""
    jd_data = _cached_artifact("jd")
    if not jd_data.get("available"):
        return {"available": False, "reason": "JD not parsed yet"}
    jd = JDParse(**jd_data)
    result = analyze_resume_fit(jd, resume_text)
    return _store("resume_fit", result)


def score_company_fit(
    *,
    company_name: str = "",
    jd_text: str = "",
    linkedin_followers: int = 0,
    alumni_hints: list[str] | None = None,
) -> dict:
    """Score company vs profile preferences (not H-1B odds)."""
    profile = get_candidate_profile()
    jd_data = _cached_artifact("jd")
    if not jd_data:
        return {"available": False, "reason": "JD not parsed"}
    jd = JDParse(**jd_data)
    sp_data = _cached_artifact("sponsorship") or {"matched": False}
    sponsorship = SponsorshipAnalysis(**sp_data)
    followers = linkedin_followers if linkedin_followers > 0 else None
    result = score_company(
        company_name or None,
        jd,
        jd_text,
        profile,
        sponsorship,
        linkedin_followers=followers,
        alumni_hints=alumni_hints or None,
    )
    return _store("company_analysis", result)


def assess_job_risks() -> dict:
    """Run deterministic risk rules on JD + resume fit."""
    profile = get_candidate_profile()
    jd_data = _cached_artifact("jd")
    rf_data = _cached_artifact("resume_fit")
    if not jd_data or not rf_data.get("available"):
        return {"available": False, "reason": "need JD parse and resume fit first"}
    jd = JDParse(**jd_data)
    resume_fit = ResumeFitAnalysis(**rf_data)
    result = run_risk_rules(jd, resume_fit, profile)
    return _store("risk", result)


def recommend_apply_skip(*, job_title: str = "", jd_text: str = "") -> dict:
    """LLM verdict with profile YAML; rules fallback when LLM unavailable."""
    profile = get_candidate_profile()
    jd_data = _cached_artifact("jd")
    rf_data = _cached_artifact("resume_fit")
    if not jd_data.get("available"):
        return {"available": False, "reason": "need JD parse first"}
    jd = JDParse(**jd_data)
    resume_fit = ResumeFitAnalysis(**rf_data) if rf_data.get("available") else ResumeFitAnalysis(available=False)
    resume_text = (get_input().get("resolved_resume") or "").strip()

    mode = (settings.recommendation_method or "auto").lower()
    if mode == "auto":
        mode = "llm" if llm_available() else "rules"
    if mode == "rules" and not resume_fit.available:
        return {"available": False, "reason": "need resume fit first (rules mode)"}
    if mode == "llm" and not resume_text:
        return {"available": False, "reason": "need resume text for LLM recommendation"}

    result = generate_recommendation(
        jd,
        resume_fit,
        profile,
        job_title or None,
        jd_text or None,
        resume_text=resume_text or None,
        job_location=(get_input().get("job_location") or None),
    )
    return _store("recommendation", result)
