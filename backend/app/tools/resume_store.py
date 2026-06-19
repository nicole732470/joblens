"""Store and retrieve resume chunks in pgvector."""

from __future__ import annotations

import hashlib

import psycopg
from pgvector.psycopg import register_vector

from app.config import settings
from app.db import fetch_all
from app.tools.embeddings import embed_texts
from app.tools.resume_chunker import chunk_resume

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS resume_chunks (
    id          TEXT PRIMARY KEY,
    resume_key  TEXT NOT NULL DEFAULT 'default',
    section     TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL,
    embedding   vector(1536),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_resume_chunks_key ON resume_chunks(resume_key);
"""


def resume_key_for(text: str) -> str:
    """Stable key for a resume body (single-user MVP)."""
    digest = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]
    return f"resume_{digest}"


def ensure_resume_schema() -> None:
    with psycopg.connect(settings.database_url) as conn:
        conn.execute(_SCHEMA_SQL)
        conn.commit()


def index_resume(text: str, resume_key: str | None = None, *, force: bool = False) -> dict:
    """Chunk, embed, and store resume text. Skips re-embed if already indexed (same key)."""
    ensure_resume_schema()
    chunks = chunk_resume(text)
    if not chunks:
        return {"indexed": False, "reason": "no chunks produced from resume text"}

    key = resume_key or resume_key_for(text)

    if not force:
        rows = fetch_all(
            "SELECT count(*)::int AS n FROM resume_chunks WHERE resume_key = %s",
            (key,),
        )
        if rows and rows[0]["n"] > 0:
            return {
                "indexed": True,
                "resume_key": key,
                "chunk_count": rows[0]["n"],
                "cached": True,
            }

    vectors = embed_texts([c["content"] for c in chunks])

    with psycopg.connect(settings.database_url) as conn:
        register_vector(conn)
        conn.execute("DELETE FROM resume_chunks WHERE resume_key = %s", (key,))
        for chunk, vector in zip(chunks, vectors, strict=True):
            conn.execute(
                """
                INSERT INTO resume_chunks (id, resume_key, section, content, embedding)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    resume_key = EXCLUDED.resume_key,
                    section = EXCLUDED.section,
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    created_at = now()
                """,
                (chunk["id"], key, chunk["section"], chunk["content"], vector),
            )
        conn.commit()

    return {"indexed": True, "resume_key": key, "chunk_count": len(chunks)}


def retrieve_resume_evidence(
    query: str,
    resume_key: str,
    *,
    limit: int = 3,
) -> list[dict]:
    """Return top resume chunks by cosine distance for a JD requirement."""
    if not (query or "").strip():
        return []

    ensure_resume_schema()
    vector = embed_texts([query.strip()])[0]

    rows = fetch_all(
        """
        SELECT id, section, content, (embedding <=> %s::vector) AS distance
        FROM resume_chunks
        WHERE resume_key = %s AND embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (vector, resume_key, vector, limit),
    )
    return [
        {
            "id": row["id"],
            "section": row["section"],
            "content": row["content"],
            "distance": float(row["distance"]),
        }
        for row in rows
    ]
