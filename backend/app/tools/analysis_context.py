"""Per-request analysis context: artifacts from tool calls + agent metadata."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from app.tools.observability import get_run_id

_agent_meta: ContextVar[dict[str, Any]] = ContextVar("analysis_agent_meta", default=None)

# Keyed by run_id — LangGraph parallel/thread nodes do not share ContextVar.
_ARTIFACTS: dict[str, dict[str, Any]] = {}
_INPUTS: dict[str, dict[str, Any]] = {}
_AGENT_META: dict[str, dict[str, Any]] = {}


def _rid() -> str | None:
    return get_run_id()


def begin_analysis(request: dict[str, Any]) -> None:
    rid = _rid()
    if rid:
        _ARTIFACTS[rid] = {}
        _INPUTS[rid] = dict(request)
        _AGENT_META[rid] = {"tool_calls": [], "llm_turns": 0}
    _agent_meta.set({"tool_calls": [], "llm_turns": 0})


def patch_input(**kwargs: Any) -> None:
    rid = _rid()
    if rid and rid in _INPUTS:
        _INPUTS[rid].update(kwargs)


def get_input() -> dict[str, Any]:
    rid = _rid()
    if rid and rid in _INPUTS:
        return dict(_INPUTS[rid])
    return {}


def get_artifacts() -> dict[str, Any]:
    rid = _rid()
    if rid and rid in _ARTIFACTS:
        return dict(_ARTIFACTS[rid])
    return {}


def set_artifact(key: str, value: Any) -> None:
    rid = _rid()
    if not rid:
        return
    store = _ARTIFACTS.setdefault(rid, {})
    store[key] = value


def get_artifact(key: str, default: Any = None) -> Any:
    return get_artifacts().get(key, default)


def record_tool_call(name: str, *, args: dict | None = None, ok: bool = True, error: str | None = None) -> None:
    rid = _rid()
    if not rid:
        return
    meta = _AGENT_META.setdefault(rid, {"tool_calls": [], "llm_turns": 0})
    entry: dict[str, Any] = {"tool": name, "ok": ok}
    if args is not None:
        entry["args_keys"] = list(args.keys())
    if error:
        entry["error"] = error
    meta["tool_calls"].append(entry)


def record_llm_turn() -> None:
    rid = _rid()
    if not rid:
        return
    meta = _AGENT_META.setdefault(rid, {"tool_calls": [], "llm_turns": 0})
    meta["llm_turns"] = int(meta.get("llm_turns", 0)) + 1


def get_agent_meta() -> dict[str, Any]:
    rid = _rid()
    if rid and rid in _AGENT_META:
        return dict(_AGENT_META[rid])
    return {"tool_calls": [], "llm_turns": 0}
