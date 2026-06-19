"""Per-request analysis context: artifacts from tool calls + agent metadata."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_artifacts: ContextVar[dict[str, Any]] = ContextVar("analysis_artifacts", default=None)
_agent_meta: ContextVar[dict[str, Any]] = ContextVar("analysis_agent_meta", default=None)
_input: ContextVar[dict[str, Any]] = ContextVar("analysis_input", default=None)


def begin_analysis(request: dict[str, Any]) -> None:
    _artifacts.set({})
    _agent_meta.set({"tool_calls": [], "llm_turns": 0})
    _input.set(dict(request))


def patch_input(**kwargs: Any) -> None:
    inp = dict(_input.get() or {})
    inp.update(kwargs)
    _input.set(inp)


def get_input() -> dict[str, Any]:
    return dict(_input.get() or {})


def get_artifacts() -> dict[str, Any]:
    return dict(_artifacts.get() or {})


def set_artifact(key: str, value: Any) -> None:
    store = _artifacts.get()
    if store is None:
        store = {}
        _artifacts.set(store)
    store[key] = value


def get_artifact(key: str, default: Any = None) -> Any:
    return get_artifacts().get(key, default)


def record_tool_call(name: str, *, args: dict | None = None, ok: bool = True, error: str | None = None) -> None:
    meta = _agent_meta.get()
    if meta is None:
        meta = {"tool_calls": [], "llm_turns": 0}
        _agent_meta.set(meta)
    entry: dict[str, Any] = {"tool": name, "ok": ok}
    if args is not None:
        entry["args_keys"] = list(args.keys())
    if error:
        entry["error"] = error
    meta["tool_calls"].append(entry)


def record_llm_turn() -> None:
    meta = _agent_meta.get() or {"tool_calls": [], "llm_turns": 0}
    meta["llm_turns"] = int(meta.get("llm_turns", 0)) + 1
    _agent_meta.set(meta)


def get_agent_meta() -> dict[str, Any]:
    return dict(_agent_meta.get() or {"tool_calls": [], "llm_turns": 0})
