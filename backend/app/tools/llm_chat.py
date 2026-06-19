"""LangChain chat model pointed at OpenRouter (tool-calling / ReAct agent)."""

from __future__ import annotations

from functools import lru_cache

from app.config import settings
from app.tools.llm import llm_available


@lru_cache(maxsize=1)
def get_chat_model():
    """ChatOpenAI compatible with OpenRouter. Returns None if no API key."""
    if not llm_available():
        return None
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0,
        max_retries=2,
        timeout=90,
    )
