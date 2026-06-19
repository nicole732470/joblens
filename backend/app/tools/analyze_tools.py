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


@tool
def lookup_h1b_sponsorship(
    company: Annotated[str, "LinkedIn company name to match against DOL H-1B records"],
) -> str:
    """Look up H-1B/LCA filing history for an employer. Returns JSON."""
    result = search_h1b_company(company)
    return json.dumps(_store("sponsorship", result, args={"company": company}), default=str)


@tool
def parse_jd_structured(
    jd_text: Annotated[str, "Full job description text"],
    title: Annotated[str, "Job title"] = "",
) -> str:
    """Extract structured requirements, location, visa language from a JD. Returns JSON."""
    result = parse_job_description(jd_text, title or None)
    return json.dumps(_store("jd", result, args={"title": title}), default=str)


@tool
def score_resume_against_jd(
    jd_parse_json: Annotated[str, "JSON from parse_jd_structured"],
    resume_text: Annotated[str, "Full resume text"],
) -> str:
    """RAG retrieval + LLM classification of resume vs each JD requirement. Returns JSON."""
    jd = JDParse(**json.loads(jd_parse_json))
    result = analyze_resume_fit(jd, resume_text)
    return json.dumps(_store("resume_fit", result), default=str)


@tool
def score_company_fit(
    company_name: Annotated[str, "Company name (empty string if unknown)"],
    jd_parse_json: Annotated[str, "JSON from parse_jd_structured"],
    jd_text: Annotated[str, "Original JD text"],
    sponsorship_json: Annotated[str, "JSON from lookup_h1b_sponsorship or {}"],
    linkedin_followers: Annotated[int, "LinkedIn follower count, 0 if unknown"] = 0,
    alumni_hints_json: Annotated[str, 'JSON array of alumni hint strings, e.g. []'] = "[]",
) -> str:
    """Score company vs profile preferences (not H-1B odds). Returns JSON."""
    profile = get_candidate_profile()
    jd = JDParse(**json.loads(jd_parse_json))
    sponsorship = SponsorshipAnalysis(**json.loads(sponsorship_json or "{}"))
    alumni = json.loads(alumni_hints_json or "[]")
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
    return json.dumps(_store("company_analysis", result), default=str)


@tool
def assess_job_risks(
    jd_parse_json: Annotated[str, "JSON from parse_jd_structured"],
    resume_fit_json: Annotated[str, "JSON from score_resume_against_jd"],
) -> str:
    """Run deterministic risk rules on JD + resume fit. Returns JSON."""
    profile = get_candidate_profile()
    jd = JDParse(**json.loads(jd_parse_json))
    resume_fit = ResumeFitAnalysis(**json.loads(resume_fit_json))
    result = run_risk_rules(jd, resume_fit, profile)
    return json.dumps(_store("risk", result), default=str)


@tool
def recommend_apply_skip(
    jd_parse_json: Annotated[str, "JSON from parse_jd_structured"],
    resume_fit_json: Annotated[str, "JSON from score_resume_against_jd"],
    job_title: Annotated[str, "Job title"] = "",
    jd_text: Annotated[str, "Original JD text"] = "",
) -> str:
    """Rule-based Apply / Near apply / Consider / Skip verdict. Returns JSON."""
    profile = get_candidate_profile()
    jd = JDParse(**json.loads(jd_parse_json))
    resume_fit = ResumeFitAnalysis(**json.loads(resume_fit_json))
    result = generate_recommendation(
        jd, resume_fit, profile, job_title or None, jd_text or None
    )
    return json.dumps(_store("recommendation", result), default=str)


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
