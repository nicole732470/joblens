"""LangChain-compatible tool wrappers for the analyze pipeline (tool-calling surface)."""

from __future__ import annotations

from typing import Annotated

from langchain_core.tools import tool

from app.tools.jd_parser import parse_job_description
from app.tools.recommendation import generate_recommendation
from app.tools.resume_fit import analyze_resume_fit
from app.tools.sponsorship import search_h1b_company


@tool
def lookup_h1b_sponsorship(company: str) -> dict:
    """Resolve a company name against DOL H-1B LCA records."""
    return search_h1b_company(company)


@tool
def parse_jd_structured(
    jd_text: Annotated[str, "Full job description text"],
    title: Annotated[str | None, "Job title if known"] = None,
) -> dict:
    """Extract structured requirements, location, and visa language from a JD."""
    return parse_job_description(jd_text, title)


@tool
def score_resume_against_jd(
    jd_parse: Annotated[dict, "JDParse-shaped dict from parse_jd_structured"],
    resume_text: Annotated[str, "Full resume markdown or plain text"],
) -> dict:
    """RAG retrieval + LLM (or vector fallback) resume–requirement fit."""
    from app.schemas.report import JDParse

    jd = JDParse(**jd_parse)
    return analyze_resume_fit(jd, resume_text)


@tool
def recommend_apply_skip(
    jd_parse: Annotated[dict, "JDParse-shaped dict"],
    resume_fit: Annotated[dict, "ResumeFitAnalysis-shaped dict"],
    job_title: Annotated[str | None, "Job title"] = None,
    jd_text: Annotated[str | None, "Original JD text"] = None,
) -> dict:
    """Rule-based Apply / Near apply / Consider / Skip from profile + fit."""
    from app.schemas.report import JDParse, ResumeFitAnalysis
    from app.tools.profile_loader import get_candidate_profile

    profile = get_candidate_profile()
    jd = JDParse(**jd_parse)
    rf = ResumeFitAnalysis(**resume_fit)
    return generate_recommendation(jd, rf, profile, job_title, jd_text)


ANALYZE_TOOLS = [
    lookup_h1b_sponsorship,
    parse_jd_structured,
    score_resume_against_jd,
    recommend_apply_skip,
]

ANALYZE_TOOLS_BY_NAME = {t.name: t for t in ANALYZE_TOOLS}
