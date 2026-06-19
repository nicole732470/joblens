"""Registered tools for ReAct agent + direct /tools API (instrumented)."""

from __future__ import annotations

import json
from typing import Annotated, Any

from langchain_core.tools import tool

from app.schemas.report import JDParse, ResumeFitAnalysis, SponsorshipAnalysis
from app.tools.analysis_context import get_artifact, record_tool_call, set_artifact
from app.tools.company_signals import score_company
from app.tools.jd_parser import parse_job_description
from app.tools.profile_loader import get_candidate_profile
from app.tools.recommendation import generate_recommendation
from app.tools.resume_fit import analyze_resume_fit
from app.tools.risk_rules import run_risk_rules
from app.tools.sponsorship import search_h1b_company


def _store(name: str, result: dict, *, args: dict | None = None) -> dict:
    set_artifact(name, result)
    record_tool_call(name, args=args, ok=bool(result.get("available", True)))
    return result


def _json_out(result: dict) -> str:
    return json.dumps(result, default=str)


def _parse_json_or_artifact(raw: str | None, artifact_key: str) -> dict:
    if raw and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    cached = get_artifact(artifact_key)
    return cached if isinstance(cached, dict) else {}


@tool
def lookup_h1b_sponsorship(
    company: Annotated[str, "LinkedIn company name to match against DOL H-1B records"],
) -> str:
    """Look up H-1B/LCA filing history for an employer."""
    result = search_h1b_company(company)
    return _json_out(_store("sponsorship", result, args={"company": company}))


@tool
def parse_jd_structured(
    jd_text: Annotated[str, "Full job description text"],
    title: Annotated[str, "Job title"] = "",
) -> str:
    """Extract structured requirements, location, visa language from a JD."""
    result = parse_job_description(jd_text, title or None)
    return _json_out(_store("jd", result, args={"title": title}))


@tool
def score_resume_against_jd(
    resume_text: Annotated[str, "Full resume text"],
    jd_parse_json: Annotated[str, "Optional — leave empty to use cached JD parse"] = "",
) -> str:
    """RAG retrieval + LLM classification of resume vs each JD requirement."""
    jd_data = _parse_json_or_artifact(jd_parse_json, "jd")
    if not jd_data.get("available"):
        return _json_out({"available": False, "reason": "JD not parsed yet — call parse_jd_structured first"})
    jd = JDParse(**jd_data)
    result = analyze_resume_fit(jd, resume_text)
    return _json_out(_store("resume_fit", result))


@tool
def score_company_fit(
    company_name: Annotated[str, "Company name (empty if unknown)"] = "",
    jd_text: Annotated[str, "Original JD text"] = "",
    linkedin_followers: Annotated[int, "LinkedIn followers, 0 if unknown"] = 0,
    alumni_hints_json: Annotated[str, 'JSON array of alumni strings, or ""'] = "",
    jd_parse_json: Annotated[str, "Optional — leave empty to use cached JD parse"] = "",
    sponsorship_json: Annotated[str, "Optional — leave empty to use cached H-1B lookup"] = "",
) -> str:
    """Score company vs profile preferences (not H-1B odds)."""
    profile = get_candidate_profile()
    jd_data = _parse_json_or_artifact(jd_parse_json, "jd")
    if not jd_data:
        return _json_out({"available": False, "reason": "JD not parsed"})
    jd = JDParse(**jd_data)
    sp_data = _parse_json_or_artifact(sponsorship_json, "sponsorship") or {"matched": False}
    sponsorship = SponsorshipAnalysis(**sp_data)
    alumni: list[str] = []
    if alumni_hints_json.strip():
        try:
            alumni = json.loads(alumni_hints_json)
        except json.JSONDecodeError:
            alumni = []
    followers = linkedin_followers if linkedin_followers > 0 else None
    result = score_company(
        company_name or None,
        jd,
        jd_text,
        profile,
        sponsorship,
        linkedin_followers=followers,
        alumni_hints=alumni or None,
    )
    return _json_out(_store("company_analysis", result))


@tool
def assess_job_risks(
    jd_parse_json: Annotated[str, "Optional — leave empty to use cached JD parse"] = "",
    resume_fit_json: Annotated[str, "Optional — leave empty to use cached resume fit"] = "",
) -> str:
    """Run deterministic risk rules on JD + resume fit."""
    profile = get_candidate_profile()
    jd_data = _parse_json_or_artifact(jd_parse_json, "jd")
    rf_data = _parse_json_or_artifact(resume_fit_json, "resume_fit")
    if not jd_data or not rf_data.get("available"):
        return _json_out({"available": False, "reason": "need JD parse and resume fit first"})
    jd = JDParse(**jd_data)
    resume_fit = ResumeFitAnalysis(**rf_data)
    result = run_risk_rules(jd, resume_fit, profile)
    return _json_out(_store("risk", result))


@tool
def recommend_apply_skip(
    job_title: Annotated[str, "Job title"] = "",
    jd_text: Annotated[str, "Original JD text"] = "",
    jd_parse_json: Annotated[str, "Optional — leave empty to use cached JD parse"] = "",
    resume_fit_json: Annotated[str, "Optional — leave empty to use cached resume fit"] = "",
) -> str:
    """Rule-based Apply / Near apply / Consider / Skip verdict."""
    profile = get_candidate_profile()
    jd_data = _parse_json_or_artifact(jd_parse_json, "jd")
    rf_data = _parse_json_or_artifact(resume_fit_json, "resume_fit")
    if not jd_data or not rf_data.get("available"):
        return _json_out({"available": False, "reason": "need JD parse and resume fit first"})
    jd = JDParse(**jd_data)
    resume_fit = ResumeFitAnalysis(**rf_data)
    result = generate_recommendation(jd, resume_fit, profile, job_title or None, jd_text or None)
    return _json_out(_store("recommendation", result))


ANALYZE_TOOLS = [
    lookup_h1b_sponsorship,
    parse_jd_structured,
    score_resume_against_jd,
    score_company_fit,
    assess_job_risks,
    recommend_apply_skip,
]

ANALYZE_TOOLS_BY_NAME = {t.name: t for t in ANALYZE_TOOLS}


def run_tool_by_name(name: str, **kwargs: Any) -> Any:
    tool = ANALYZE_TOOLS_BY_NAME.get(name)
    if tool is None:
        raise KeyError(f"unknown tool: {name}")
    return tool.invoke(kwargs)
