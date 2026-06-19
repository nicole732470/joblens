"""Persist traces, optional LangSmith, structured logging."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger("hop.analyze")

_trace: ContextVar[list[dict[str, Any]] | None] = ContextVar("_trace", default=None)
_run_id: ContextVar[str | None] = ContextVar("_run_id", default=None)
_trace_meta: ContextVar[dict[str, Any]] = ContextVar("_trace_meta", default=None)


def configure_langsmith() -> bool:
    """Enable LangSmith tracing when API key is set (optional)."""
    if not settings.langsmith_api_key:
        return False
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_API_KEY", settings.langsmith_api_key)
    if settings.langsmith_project:
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.langsmith_project)
    return True


def start_trace() -> str:
    run_id = uuid.uuid4().hex[:12]
    _run_id.set(run_id)
    _trace.set([])
    _trace_meta.set({"started_at": datetime.now(UTC).isoformat()})
    return run_id


def get_run_id() -> str | None:
    return _run_id.get()


def get_trace_steps() -> list[dict[str, Any]]:
    return list(_trace.get() or [])


@contextmanager
def trace_step(name: str, **meta: Any):
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
            "hop step=%s ms=%.1f run_id=%s %s",
            name,
            elapsed_ms,
            _run_id.get(),
            meta,
        )


def trace_snapshot(*, agent_meta: dict | None = None) -> dict[str, Any]:
    steps = get_trace_steps()
    total_ms = sum(s.get("duration_ms", 0) for s in steps)
    meta = dict(_trace_meta.get() or {})
    snap = {
        "run_id": get_run_id(),
        "started_at": meta.get("started_at"),
        "total_duration_ms": round(total_ms, 1),
        "steps": steps,
        "langsmith_enabled": bool(settings.langsmith_api_key),
    }
    if agent_meta:
        snap["agent"] = agent_meta
    return snap


def persist_trace(payload: dict[str, Any]) -> str | None:
    """Write full trace JSON to disk; returns file path."""
    run_id = payload.get("run_id") or get_run_id()
    if not run_id:
        return None
    base = Path(settings.trace_dir)
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{run_id}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return str(path)


def list_recent_traces(limit: int = 20) -> list[dict[str, Any]]:
    base = Path(settings.trace_dir)
    if not base.exists():
        return []
    files = sorted(base.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[dict[str, Any]] = []
    for path in files[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            out.append(
                {
                    "run_id": data.get("run_id", path.stem),
                    "started_at": data.get("observability", {}).get("started_at"),
                    "status": data.get("status"),
                    "path": str(path),
                }
            )
        except Exception:  # noqa: BLE001
            out.append({"run_id": path.stem, "path": str(path)})
    return out


def load_trace(run_id: str) -> dict[str, Any] | None:
    path = Path(settings.trace_dir) / f"{run_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
