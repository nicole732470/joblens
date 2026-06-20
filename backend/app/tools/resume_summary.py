"""Short resume blurb for report UI."""

from __future__ import annotations


def resume_summary(text: str | None, *, max_len: int = 320) -> str:
    if not text or not text.strip():
        return ""
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
        if len(lines) >= 4:
            break
    summary = " ".join(lines)
    if len(summary) > max_len:
        return summary[: max_len - 1].rstrip() + "…"
    return summary
