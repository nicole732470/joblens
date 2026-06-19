"""Thin OpenAI-compatible LLM client.

Points at whatever `LLM_BASE_URL` is configured (OpenRouter free tier by
default). Kept provider-agnostic so deploying to OpenAI / a Bedrock proxy later
is just an env change. Returns raw JSON text; callers validate against Pydantic.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Optional

from app.config import settings


@lru_cache(maxsize=1)
def get_client():
    """Construct the client once, or None if no API key is configured."""
    if not settings.llm_api_key:
        return None
    from openai import OpenAI

    return OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)


def llm_available() -> bool:
    return bool(settings.llm_api_key)


def _extract_json(text: str) -> dict:
    """Best-effort: parse JSON, falling back to the outermost {...} block.

    Free models sometimes wrap JSON in prose or markdown fences.
    """
    text = (text or "").strip()
    try:
        return json.loads(text)
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

    resp = client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=max_tokens,
    )
    msg = resp.choices[0].message
    # Thinking models put output in `reasoning`, not `content`.
    content: Optional[str] = msg.content or getattr(msg, "reasoning", None)
    if not content:
        raise ValueError("empty response from model")
    return _extract_json(content)
