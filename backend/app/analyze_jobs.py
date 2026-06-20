"""In-memory async analyze jobs (poll from web to avoid gateway timeouts)."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

_lock = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}
_TTL_SEC = 3600


def _prune() -> None:
    now = time.time()
    stale = [k for k, v in _JOBS.items() if now - v.get("created_at", now) > _TTL_SEC]
    for k in stale:
        _JOBS.pop(k, None)


def create_job(*, run_id: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _prune()
        _JOBS[job_id] = {
            "job_id": job_id,
            "run_id": run_id,
            "status": "running",
            "phase": "starting",
            "message": "Starting analysis…",
            "report": None,
            "error": None,
            "created_at": time.time(),
        }
    return job_id


def get_job(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def update_job(job_id: str, **fields: Any) -> None:
    with _lock:
        if job_id in _JOBS:
            _JOBS[job_id].update(fields)


def finish_job(job_id: str, *, report: dict[str, Any]) -> None:
    update_job(job_id, status="done", phase="complete", message="Done", report=report)


def fail_job(job_id: str, *, error: str) -> None:
    update_job(job_id, status="error", phase="failed", message=error, error=error)
