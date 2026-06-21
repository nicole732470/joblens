"""External company evidence discovery.

Tavily finds sources; it does not score Company fit. Returned evidence is kept
small and source-addressable so the scoring model can cite what it used.
"""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from time import time
from typing import Any

import httpx

from app.config import settings

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = Lock()


def tavily_available() -> bool:
    return bool(settings.tavily_api_key)


def research_company(company_name: str) -> dict[str, Any]:
    name = (company_name or "").strip()
    if not name:
        return {"available": False, "reason": "no company name", "sources": []}
    if not tavily_available():
        return {"available": False, "reason": "Tavily not configured", "sources": []}

    cache_key = name.casefold()
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
    ttl_seconds = max(1, settings.company_research_ttl_hours) * 3600
    if cached and time() - cached[0] < ttl_seconds:
        return {**cached[1], "cached": True}

    query = (
        f'"{name}" company official website industry products employee count '
        "funding investors ownership public private headquarters"
    )
    payload = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "search_depth": settings.tavily_search_depth,
        "max_results": settings.tavily_max_results,
        "include_answer": False,
        "include_raw_content": False,
        "topic": "general",
    }
    try:
        response = httpx.post(
            "https://api.tavily.com/search",
            json=payload,
            timeout=20.0,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "reason": f"Tavily research failed: {type(exc).__name__}",
            "sources": [],
        }

    retrieved_at = datetime.now(UTC).isoformat()
    sources: list[dict[str, str]] = []
    for row in data.get("results") or []:
        url = str(row.get("url") or "").strip()
        content = str(row.get("content") or "").strip()
        if not url or not content:
            continue
        sources.append(
            {
                "title": str(row.get("title") or url).strip()[:240],
                "url": url[:1000],
                "content": content[:1800],
                "retrieved_at": retrieved_at,
            }
        )

    result = {
        "available": bool(sources),
        "reason": None if sources else "Tavily returned no usable evidence",
        "query": query,
        "sources": sources,
        "retrieved_at": retrieved_at,
        "cached": False,
    }
    if sources:
        with _CACHE_LOCK:
            _CACHE[cache_key] = (time(), result)
    return result
