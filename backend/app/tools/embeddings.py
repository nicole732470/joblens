"""OpenAI-compatible text embeddings for resume RAG."""

from app.config import settings
from app.tools.llm import get_client, llm_available


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of strings. Raises RuntimeError if LLM/embeddings not configured."""
    if not texts:
        return []
    if not llm_available():
        raise RuntimeError("LLM not configured (set LLM_API_KEY for embeddings)")

    client = get_client()
    resp = client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
    )
    # API returns embeddings ordered by index.
    ordered = sorted(resp.data, key=lambda row: row.index)
    return [row.embedding for row in ordered]
