"""Split resume text into citable chunks for embedding."""

from __future__ import annotations

import re

_MIN_CHARS = 80
_MAX_CHARS = 1200


def chunk_resume(text: str) -> list[dict]:
    """Return [{id, section, content}, …] from raw resume text."""
    text = (text or "").strip()
    if not text:
        return []

    blocks = re.split(r"\n\s*\n", text)
    chunks: list[dict] = []
    buffer = ""
    section = "experience"

    def flush():
        nonlocal buffer
        body = buffer.strip()
        if len(body) >= _MIN_CHARS:
            idx = len(chunks) + 1
            chunks.append(
                {
                    "id": f"resume_chunk_{idx:02d}",
                    "section": section,
                    "content": body,
                }
            )
        buffer = ""

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # Treat markdown-style headings as section markers.
        heading = re.match(r"^#{1,3}\s+(.+)$", block)
        if heading:
            flush()
            section = heading.group(1).strip().lower()
            continue

        if len(buffer) + len(block) + 2 <= _MAX_CHARS:
            buffer = f"{buffer}\n\n{block}".strip() if buffer else block
        else:
            flush()
            if len(block) > _MAX_CHARS:
                for i in range(0, len(block), _MAX_CHARS):
                    part = block[i : i + _MAX_CHARS].strip()
                    if len(part) >= _MIN_CHARS:
                        idx = len(chunks) + 1
                        chunks.append(
                            {
                                "id": f"resume_chunk_{idx:02d}",
                                "section": section,
                                "content": part,
                            }
                        )
            else:
                buffer = block

    flush()
    return chunks
