"""LangGraph workflow for POST /analyze."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.schemas.candidate_profile import CandidateProfile
from app.schemas.report import (
    CompanyAnalysis,
    JDParse,
    RecommendationResult,
    Report,
    ResumeFitAnalysis,
    RiskAnalysis,
    SponsorshipAnalysis,
)
from app.tools.analyze_tools import ANALYZE_TOOLS, ANALYZE_TOOLS_BY_NAME
from app.tools.company_signals import score_company
from app.tools.jd_parser import parse_job_description
from app.tools.observability import trace_snapshot, trace_step
from app.tools.profile_loader import get_candidate_profile
from app.tools.recommendation import generate_recommendation
from app.tools.resume_fit import analyze_resume_fit
from app.tools.resume_loader import resolve_resume_text
from app.tools.risk_rules import run_risk_rules
from app.tools.sponsorship import search_h1b_company


class AnalyzeState(TypedDict, total=False):
    company: str | None
    title: str | None
    jd_text: str
    resume_text: str | None
    job_url: str | None
    linkedin_followers: int | None
    alumni_hints: list[str]

    sponsorship: dict
    jd: dict
    resume_source: str | None
    resolved_resume: str | None
    resume_fit: dict
    profile: CandidateProfile | None
    company_analysis: dict
    risk: dict
    recommendation: dict
    pending: list[str]
    tool_calls: list[dict]


def _node_sponsorship(state: AnalyzeState) -> dict:
    with trace_step("sponsorship_lookup", company=state.get("company")):
        if state.get("company"):
            result = search_h1b_company(state["company"])
        else:
            result = {"matched": False, "reason": "no company provided"}
    return {"sponsorship": result}


def _node_parse_jd(state: AnalyzeState) -> dict:
    with trace_step("parse_jd", title=state.get("title")):
        result = parse_job_description(state["jd_text"], state.get("title"))
    pending = list(state.get("pending") or [])
    if not result.get("available"):
        pending.append("jd_parsing")
    return {"jd": result, "pending": pending}


def _node_resume_fit(state: AnalyzeState) -> dict:
    pending = list(state.get("pending") or [])
    resolved, source = resolve_resume_text(state.get("resume_text"))
    if not resolved:
        pending.append("resume_fit")
        return {
            "resolved_resume": None,
            "resume_source": source,
            "resume_fit": {"available": False, "reason": "no resume text"},
            "pending": pending,
        }

    jd = JDParse(**state["jd"])
    with trace_step("resume_fit", resume_source=source):
        try:
            fit = analyze_resume_fit(jd, resolved)
        except Exception as e:  # noqa: BLE001
            fit = {"available": False, "reason": str(e)}
            pending.append("resume_fit")

    if not fit.get("available"):
        pending.append("resume_fit")

    return {
        "resolved_resume": resolved,
        "resume_source": source,
        "resume_fit": fit,
        "pending": pending,
        "tool_calls": [
            {
                "tool": "score_resume_against_jd",
                "match_method": fit.get("match_method"),
                "available": fit.get("available"),
            }
        ],
    }


def _node_profile(state: AnalyzeState) -> dict:
    with trace_step("load_profile"):
        try:
            profile = get_candidate_profile()
        except Exception:
            profile = None
    pending = list(state.get("pending") or [])
    if profile is None:
        pending.append("recommendation")
    return {"profile": profile, "pending": pending}


def _node_company_and_risk(state: AnalyzeState) -> dict:
    profile = state.get("profile")
    if profile is None:
        return {
            "company_analysis": {"available": False, "reason": "no profile"},
            "risk": {"available": False, "reason": "no profile"},
        }

    jd = JDParse(**state["jd"])
    sponsorship = SponsorshipAnalysis(**state["sponsorship"])
    resume_fit = ResumeFitAnalysis(**state["resume_fit"])

    with trace_step("score_company"):
        try:
            company = score_company(
                state.get("company"),
                jd,
                state["jd_text"],
                profile,
                sponsorship,
                linkedin_followers=state.get("linkedin_followers"),
                alumni_hints=state.get("alumni_hints") or None,
            )
        except Exception as e:  # noqa: BLE001
            company = {"available": False, "reason": str(e)}

    with trace_step("risk_rules"):
        try:
            risk = run_risk_rules(jd, resume_fit, profile)
        except Exception as e:  # noqa: BLE001
            risk = {"available": False, "reason": str(e)}

    return {"company_analysis": company, "risk": risk}


def _node_recommend(state: AnalyzeState) -> dict:
    profile = state.get("profile")
    pending = list(state.get("pending") or [])
    if profile is None:
        return {"recommendation": {"available": False, "reason": "no profile"}, "pending": pending}

    jd = JDParse(**state["jd"])
    resume_fit = ResumeFitAnalysis(**state["resume_fit"])
    with trace_step("recommend"):
        try:
            rec = generate_recommendation(
                jd, resume_fit, profile, state.get("title"), state["jd_text"]
            )
        except Exception as e:  # noqa: BLE001
            rec = {"available": False, "reason": str(e)}
            pending.append("recommendation")

    if not rec.get("available"):
        pending.append("recommendation")

    tool_calls = list(state.get("tool_calls") or [])
    tool_calls.append({"tool": "recommend_apply_skip", "decision": rec.get("decision")})

    return {"recommendation": rec, "pending": pending, "tool_calls": tool_calls}


def _build_graph():
    graph = StateGraph(AnalyzeState)
    graph.add_node("sponsorship", _node_sponsorship)
    graph.add_node("parse_jd", _node_parse_jd)
    graph.add_node("resume_fit", _node_resume_fit)
    graph.add_node("profile", _node_profile)
    graph.add_node("company_risk", _node_company_and_risk)
    graph.add_node("recommend", _node_recommend)

    graph.set_entry_point("sponsorship")
    graph.add_edge("sponsorship", "parse_jd")
    graph.add_edge("parse_jd", "resume_fit")
    graph.add_edge("resume_fit", "profile")
    graph.add_edge("profile", "company_risk")
    graph.add_edge("company_risk", "recommend")
    graph.add_edge("recommend", END)
    return graph.compile()


_GRAPH = None


def get_analyze_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    return _GRAPH


def run_tool_by_name(name: str, **kwargs: Any) -> Any:
    """Invoke a registered analyze tool by name (tool-calling entry point)."""
    tool = ANALYZE_TOOLS_BY_NAME.get(name)
    if tool is None:
        raise KeyError(f"unknown tool: {name}")
    return tool.invoke(kwargs)


def run_analyze_workflow(
    *,
    jd_text: str,
    company_name: str | None,
    title: str | None,
    resume_text: str | None,
    job_url: str | None,
    linkedin_followers: int | None,
    alumni_hints: list[str],
    build_explain,
) -> Report:
    initial: AnalyzeState = {
        "jd_text": jd_text,
        "company": company_name,
        "title": title,
        "resume_text": resume_text,
        "job_url": job_url,
        "linkedin_followers": linkedin_followers,
        "alumni_hints": alumni_hints,
        "pending": [],
        "tool_calls": [],
    }

    with trace_step("langgraph_invoke"):
        final = get_analyze_graph().invoke(initial)

    pending = list(final.get("pending") or [])
    status = "complete" if not pending else "partial"

    sponsorship = SponsorshipAnalysis(**final["sponsorship"])
    jd = JDParse(**final["jd"])
    resume_fit = ResumeFitAnalysis(**final.get("resume_fit") or {})
    risk = RiskAnalysis(**final.get("risk") or {})
    company_analysis = CompanyAnalysis(**final.get("company_analysis") or {})
    recommendation = RecommendationResult(**final.get("recommendation") or {})
    profile = final.get("profile")

    explain = build_explain(recommendation, company_analysis) if profile is not None else {}
    if explain is not None:
        explain = {
            **explain,
            "resume_fit": {
                "match_method": resume_fit.match_method,
                "note": (
                    "llm = RAG retrieves top-k resume chunks (embeddings), then LLM "
                    "judges each requirement; vector = distance thresholds only."
                ),
            },
            "pipeline": final.get("tool_calls"),
            "observability": trace_snapshot(),
        }

    return Report(
        status=status,
        pending=pending,
        sponsorship=sponsorship,
        company=company_analysis,
        jd=jd,
        resume_fit=resume_fit,
        risk=risk,
        recommendation=recommendation,
        received={
            "company": company_name,
            "title": title,
            "jd_chars": len(jd_text),
            "has_resume": final.get("resolved_resume") is not None,
            "resume_source": final.get("resume_source"),
            "job_url": job_url,
            "linkedin_followers": linkedin_followers,
            "alumni_hints": alumni_hints,
        },
        explain=explain,
    )


def list_analyze_tools() -> list[dict[str, str]]:
    return [{"name": t.name, "description": t.description or ""} for t in ANALYZE_TOOLS]
