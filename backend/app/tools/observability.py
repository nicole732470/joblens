"""Structured pipeline tracing for /analyze (observability)."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

logger = logging.getLogger("hop.analyze")

_trace: ContextVar[list[dict[str, Any]] | None] = ContextVar("_trace", default=None)
_run_id: ContextVar[str | None] = ContextVar("_run_id", default=None)


def start_trace() -> str:
    run_id = uuid.uuid4().hex[:12]
    _run_id.set(run_id)
    _trace.set([])
    return run_id


def get_run_id() -> str | None:
    return _run_id.get()


def get_trace_steps() -> list[dict[str, Any]]:
    return list(_trace.get() or [])


@contextmanager
def trace_step(name: str, **meta: Any):
    """Record step name, duration_ms, and optional metadata into the active trace."""
    started = time.perf_counter()
    error: str | None = None
    try:
        yield
    except Exception as e:  # noqa: BLE001
        error = str(e)
        raise
    finally:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        steps = _trace.get()
        if steps is not None:
            entry: dict[str, Any] = {
                "step": name,
                "duration_ms": elapsed_ms,
                **{k: v for k, v in meta.items() if v is not None},
            }
            if error:
                entry["error"] = error
            steps.append(entry)
        logger.info(
            "analyze step=%s duration_ms=%s run_id=%s %s",
            name,
            elapsed_ms,
            _run_id.get(),
            meta,
        )


def trace_snapshot() -> dict[str, Any]:
    return {"run_id": get_run_id(), "steps": get_trace_steps()}
