"""ReAct agent: LLM chooses and invokes analyze tools."""

from __future__ import annotations

import json
from functools import lru_cache

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from app.tools.analysis_context import get_artifacts, get_input, record_llm_turn
from app.tools.analyze_tools import ANALYZE_TOOLS
from app.tools.llm_chat import get_chat_model
from app.tools.observability import trace_step

_AGENT_SYSTEM = """You are Hop's job-analysis agent. You MUST complete a full analysis by calling tools.

Workflow (call each required tool once, in order, passing JSON outputs forward):
1. lookup_h1b_sponsorship — if company name is provided (skip if empty)
2. parse_jd_structured — unless JD parse JSON is already supplied below
3. score_resume_against_jd — requires jd_parse_json + resume_text
4. score_company_fit — company + jd + sponsorship JSON + followers + alumni JSON
5. assess_job_risks — jd_parse_json + resume_fit_json
6. recommend_apply_skip — jd_parse_json + resume_fit_json + title + jd_text

Rules:
- Pass full JSON strings between tools exactly as returned.
- Use resume_text from the user context for score_resume_against_jd.
- For empty company use company_name="" and sponsorship_json='{"matched":false}'.
- Do not invent data. After all tools succeed, reply with a one-line summary only.
"""


def _serialize_messages(messages: list) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        if isinstance(m, HumanMessage):
            out.append({"role": "human", "content": str(m.content)[:500]})
        elif isinstance(m, AIMessage):
            entry: dict = {"role": "assistant", "content": str(m.content or "")[:500]}
            if m.tool_calls:
                entry["tool_calls"] = [tc.get("name") for tc in m.tool_calls]
            out.append(entry)
        elif isinstance(m, ToolMessage):
            out.append({"role": "tool", "name": m.name, "content_len": len(str(m.content))})
    return out


@lru_cache(maxsize=1)
def get_react_agent():
    model = get_chat_model()
    if model is None:
        return None
    return create_react_agent(model, ANALYZE_TOOLS)


def _build_agent_prompt(state: dict) -> str:
    inp = get_input()
    arts = get_artifacts()
    lines = [
        _AGENT_SYSTEM,
        "",
        "## Request context",
        f"company: {inp.get('company') or ''}",
        f"title: {inp.get('title') or ''}",
        f"jd_text_chars: {len(inp.get('jd_text') or '')}",
        f"resume_available: {bool(inp.get('resolved_resume'))}",
        f"resume_source: {inp.get('resume_source')}",
        f"linkedin_followers: {inp.get('linkedin_followers') or 0}",
        f"alumni_hints_json: {json.dumps(inp.get('alumni_hints') or [])}",
        "",
        "## Prefetched artifacts (use instead of re-calling if present)",
    ]
    if arts.get("sponsorship"):
        lines.append(f"sponsorship_json: {json.dumps(arts['sponsorship'], default=str)[:2000]}")
    if arts.get("jd"):
        lines.append(f"jd_parse_json: {json.dumps(arts['jd'], default=str)[:4000]}")
    if inp.get("resolved_resume"):
        resume = inp["resolved_resume"]
        lines.append(f"resume_text: {resume[:6000]}")
    lines.append(f"jd_text: {(inp.get('jd_text') or '')[:8000]}")
    lines.append("")
    lines.append("Begin tool calls now.")
    return "\n".join(lines)


def run_react_agent(state: dict) -> dict:
    """Invoke ReAct loop; tools write into analysis_context artifacts."""
    agent = get_react_agent()
    if agent is None:
        return {"agent_mode": "skipped", "agent_reason": "no_llm_key", "agent_messages": []}

    with trace_step("react_agent"):
        record_llm_turn()
        result = agent.invoke(
            {"messages": [HumanMessage(content=_build_agent_prompt(state))]},
            config={"recursion_limit": 25},
        )

    messages = result.get("messages") or []
    return {
        "agent_mode": "react",
        "agent_messages": _serialize_messages(messages),
    }
