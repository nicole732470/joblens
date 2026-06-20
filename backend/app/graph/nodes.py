"""LangGraph nodes — parallel prefetch + deterministic analyze pipeline."""

from __future__ import annotations

from app.config import settings
from app.graph.state_helpers import bind_node, request_fields
from app.tools.analysis_context import get_artifacts, get_input, patch_input, record_tool_call, set_artifact
from app.tools.analyze_tools import (
    assess_job_risks,
    lookup_h1b_sponsorship,
    parse_jd_structured,
    recommend_apply_skip,
    score_company_fit,
    score_resume_against_jd,
)
from app.tools.jd_parser import parse_job_description
from app.tools.llm import llm_available
from app.tools.observability import trace_step
from app.tools.profile_loader import get_candidate_profile
from app.tools.resume_loader import resolve_resume_text
from app.tools.sponsorship import search_h1b_company


def node_prepare(state: dict) -> dict:
    bind_node(state)
    req = request_fields(state)
    with trace_step("prepare"):
        resolved, source = resolve_resume_text(req.get("resume_text"))
        profile = None
        try:
            profile = get_candidate_profile()
        except Exception:  # noqa: BLE001
            pass
        patch_input(resolved_resume=resolved, resume_source=source)
    return {
        "resolved_resume": resolved,
        "resume_source": source,
        "profile_loaded": profile is not None,
        "parse_attempts": 0,
    }


def node_sponsorship(state: dict) -> dict:
    bind_node(state)
    company = request_fields(state).get("company")
    with trace_step("sponsorship_lookup", company=company):
        if company:
            result = search_h1b_company(company)
        else:
            result = {"matched": False, "reason": "no company provided"}
    set_artifact("sponsorship", result)
    record_tool_call("lookup_h1b_sponsorship", args={"company": company}, ok=True)
    return {"sponsorship": result}


def node_parse_jd(state: dict) -> dict:
    bind_node(state)
    req = request_fields(state)
    attempts = int(state.get("parse_attempts") or 0) + 1
    with trace_step("parse_jd", attempt=attempts, title=req.get("title")):
        result = parse_job_description(
            req.get("jd_text") or "",
            req.get("title"),
            req.get("job_location"),
        )
    set_artifact("jd", result)
    record_tool_call("parse_jd_structured", ok=bool(result.get("available")))
    return {"jd": result, "parse_attempts": attempts}


def route_after_parse(state: dict) -> str:
    jd = state.get("jd") or {}
    attempts = int(state.get("parse_attempts") or 0)
    missing_reqs = not (jd.get("requirements") or [])
    if not jd.get("available") and attempts < 2:
        reason = (jd.get("reason") or "").lower()
        if "no requirements extracted" in reason or "no job description" in reason:
            return "continue"
        return "retry_parse"
    if jd.get("available") and missing_reqs and attempts < 2:
        return "retry_parse"
    return "continue"


def node_join(state: dict) -> dict:
    bind_node(state)
    with trace_step("join_prefetch"):
        pass
    return {}


def node_analyze(state: dict) -> dict:
    """Run remaining pipeline steps in fixed order."""
    bind_node(state)
    inp = get_input()
    arts = get_artifacts()
    company = inp.get("company") or ""
    title = inp.get("title") or ""
    jd_text = inp.get("jd_text") or ""
    resume = inp.get("resolved_resume") or ""

    with trace_step("analyze_pipeline"):
        if "sponsorship" not in arts and company:
            lookup_h1b_sponsorship(company)
        elif "sponsorship" not in arts:
            set_artifact("sponsorship", {"matched": False, "reason": "no company"})

        jd_art = arts.get("jd") or {}
        if not jd_art.get("available") or not (jd_art.get("requirements") or []):
            parse_jd_structured(jd_text, title)

        if resume and ("resume_fit" not in arts or not arts.get("resume_fit", {}).get("available")):
            score_resume_against_jd(resume)

        arts = get_artifacts()

        if "company_analysis" not in arts or not arts.get("company_analysis", {}).get("available"):
            score_company_fit(
                company_name=company,
                jd_text=jd_text,
                linkedin_followers=int(inp.get("linkedin_followers") or 0),
                alumni_hints=inp.get("alumni_hints") or None,
            )

        arts = get_artifacts()

        if "risk" not in arts or not arts.get("risk", {}).get("available"):
            if arts.get("resume_fit", {}).get("available"):
                assess_job_risks()

        arts = get_artifacts()

        if "recommendation" not in arts or not arts.get("recommendation", {}).get("available"):
            jd_ok = arts.get("jd", {}).get("available")
            rf_ok = arts.get("resume_fit", {}).get("available")
            mode = (settings.recommendation_method or "auto").lower()
            if mode == "auto":
                mode = "llm" if llm_available() else "rules"
            can_recommend = jd_ok and (rf_ok or (mode == "llm" and bool(resume)))
            if can_recommend:
                recommend_apply_skip(job_title=title, jd_text=jd_text)

    return {"pipeline_complete": True}
