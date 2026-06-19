"""Thin OpenAI-compatible LLM client.

Points at whatever `LLM_BASE_URL` is configured (OpenRouter free tier by
default). Kept provider-agnostic so deploying to OpenAI / a Bedrock proxy later
is just an env change. Returns raw JSON text; callers validate against Pydantic.
"""

from __future__ import annotations

import json
import re
import time
from functools import lru_cache
from typing import Optional

from app.config import settings


@lru_cache(maxsize=1)
def get_client():
    """Construct the client once, or None if no API key is configured."""
    if not settings.llm_api_key:
        return None
    from openai import OpenAI

    return OpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        timeout=45.0,
        max_retries=1,
    )


def llm_available() -> bool:
    return bool(settings.llm_api_key)


def _extract_json(text: str) -> dict:
    """Best-effort: parse JSON from model output (incl. markdown fences / prose)."""
    text = (text or "").strip()
    if not text:
        raise ValueError("empty response from model")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # ```json ... ``` or ``` ... ```
    for pattern in (r"```json\s*([\s\S]*?)```", r"```\s*([\s\S]*?)```"):
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass

    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError("no JSON object found in model response")


def complete_json(system: str, user: str, max_tokens: int = 1500) -> dict:
    """Call the chat model and return parsed JSON.

    Raises RuntimeError if the LLM isn't configured, or ValueError/JSONDecodeError
    if the response can't be parsed.
    """
    client = get_client()
    if client is None:
        raise RuntimeError("LLM not configured (set LLM_API_KEY)")

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    def _call(use_json_mode: bool):
        kwargs: dict = {
            "model": settings.llm_model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        if use_json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        return client.chat.completions.create(**kwargs)

    try:
        resp = _call(True)
    except Exception:
        # Many OpenRouter free providers don't support response_format; fall back
        # to a plain call and lean on the prompt + _extract_json.
        resp = _call(False)

    msg = resp.choices[0].message
    # Thinking models may split output across content and reasoning.
    content: Optional[str] = msg.content or ""
    reasoning = getattr(msg, "reasoning", None) or ""
    merged = content.strip()
    if reasoning.strip():
        merged = f"{merged}\n{reasoning}".strip() if merged else reasoning.strip()
    if not merged:
        raise ValueError("empty response from model")
    return _extract_json(merged)


def complete_json_with_retry(
    system: str,
    user: str,
    *,
    max_attempts: int = 3,
    base_delay_sec: float = 0.8,
    max_tokens: int = 1500,
) -> dict:
    """Call complete_json with exponential backoff on transient failures.

    Attempts: 3 by default, delays ~0.8s, ~1.6s between tries (before last).
    """
    last_err: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return complete_json(system, user, max_tokens=max_tokens)
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < max_attempts - 1:
                time.sleep(base_delay_sec * (2**attempt))
    assert last_err is not None
    raise last_err
