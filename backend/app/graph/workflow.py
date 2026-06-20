"""LangGraph workflow: parallel H-1B + JD prefetch, then deterministic analyze pipeline."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.graph.assemble import assemble_report
from app.graph.nodes import (
    node_analyze,
    node_join,
    node_parse_jd,
    node_prepare,
    node_sponsorship,
    route_after_parse,
)
from app.graph.state_helpers import bind_node
from app.schemas.report import Report
from app.tools.analysis_context import begin_analysis, get_agent_meta
from app.tools.observability import get_run_id, persist_trace, trace_snapshot, trace_step


class AnalyzeState(TypedDict, total=False):
    run_id: str | None
    jd_text: str
    company: str | None
    title: str | None
    resume_text: str | None
    resume_filename: str | None
    job_url: str | None
    job_location: str | None
    linkedin_followers: int | None
    alumni_hints: list[str]
    resolved_resume: str | None
    resume_source: str | None
    profile_loaded: bool
    parse_attempts: int
    sponsorship: dict
    jd: dict
    pipeline_complete: bool
    report: Any
    observability: dict


def _fan_out_prefetch(state: dict) -> list[Send]:
    return [
        Send("sponsorship", state),
        Send("parse_jd", state),
    ]


def _node_assemble(state: dict, *, build_explain) -> dict:
    bind_node(state)
    run_id = state.get("run_id")
    pipeline_meta = {**get_agent_meta(), "mode": "deterministic"}
    obs = trace_snapshot(run_id=run_id, agent_meta=pipeline_meta)
    report = assemble_report(
        build_explain=build_explain,
        agent_meta=pipeline_meta,
        observability=obs,
    )
    payload = report.model_dump()
    payload["run_id"] = run_id or obs.get("run_id")
    payload["observability"] = obs
    path = persist_trace(payload)
    if path:
        obs["trace_file"] = path
    return {"report": report, "observability": obs}


def _build_graph(build_explain):
    graph = StateGraph(AnalyzeState)

    def assemble_node(state: dict) -> dict:
        return _node_assemble(state, build_explain=build_explain)

    graph.add_node("prepare", node_prepare)
    graph.add_node("sponsorship", node_sponsorship)
    graph.add_node("parse_jd", node_parse_jd)
    graph.add_node("join", node_join)
    graph.add_node("analyze", node_analyze)
    graph.add_node("assemble", assemble_node)

    graph.add_edge(START, "prepare")
    graph.add_conditional_edges("prepare", _fan_out_prefetch, ["sponsorship", "parse_jd"])
    graph.add_edge("sponsorship", "join")
    graph.add_edge("parse_jd", "join")

    graph.add_conditional_edges(
        "join",
        route_after_parse,
        {"retry_parse": "parse_jd", "continue": "analyze"},
    )
    graph.add_edge("analyze", "assemble")
    graph.add_edge("assemble", END)

    return graph.compile()


_GRAPH = None
_BUILD_EXPLAIN = None


def get_analyze_graph(build_explain):
    global _GRAPH, _BUILD_EXPLAIN
    if _GRAPH is None or _BUILD_EXPLAIN is not build_explain:
        _BUILD_EXPLAIN = build_explain
        _GRAPH = _build_graph(build_explain)
    return _GRAPH


def run_analyze_workflow(
    *,
    jd_text: str,
    company_name: str | None,
    title: str | None,
    resume_text: str | None,
    resume_filename: str | None = None,
    job_url: str | None,
    job_location: str | None,
    linkedin_followers: int | None,
    alumni_hints: list[str],
    build_explain,
) -> Report:
    begin_analysis(
        {
            "jd_text": jd_text,
            "company": company_name,
            "title": title,
            "resume_text": resume_text,
            "resume_filename": resume_filename,
            "job_url": job_url,
            "job_location": job_location,
            "linkedin_followers": linkedin_followers,
            "alumni_hints": alumni_hints,
        }
    )

    run_id = get_run_id()
    initial: dict[str, Any] = {
        "run_id": run_id,
        "jd_text": jd_text,
        "company": company_name,
        "title": title,
        "resume_text": resume_text,
        "resume_filename": resume_filename,
        "job_url": job_url,
        "job_location": job_location,
        "linkedin_followers": linkedin_followers,
        "alumni_hints": alumni_hints,
        "parse_attempts": 0,
    }

    with trace_step("langgraph_invoke"):
        final = get_analyze_graph(build_explain).invoke(initial)

    report = final.get("report")
    if isinstance(report, Report):
        return report
    if isinstance(report, dict):
        return Report(**report)
    raise RuntimeError("analyze workflow did not produce a report")
