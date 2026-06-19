"""Helper to bind LangGraph worker threads + read request fields."""

from __future__ import annotations

from app.tools.analysis_context import get_input
from app.tools.observability import bind_run_id


def bind_node(state: dict) -> None:
    bind_run_id(state.get("run_id"))


def request_fields(state: dict) -> dict:
    """Merge graph state with analysis_context input (parallel nodes may drop keys)."""
    return {**get_input(), **state}
