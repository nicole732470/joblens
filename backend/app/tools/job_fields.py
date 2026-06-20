"""Normalize company / title / location — same rules as shared/report-view.js."""

from __future__ import annotations

import re

_HIRING_TITLE_RE = re.compile(r"^(.+?)\s+hiring\s+(.+?)\s+in\s+(.+)$", re.IGNORECASE)


def normalize_job_fields(
    company: str | None,
    title: str | None,
    job_location: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Parse LinkedIn-style titles: ``Acme Corp hiring Engineer in Austin, TX``."""
    t = re.sub(r"\s*\|\s*LinkedIn\s*$", "", (title or ""), flags=re.IGNORECASE).strip()
    c = (company or "").strip()
    if c.lower() == "linkedin":
        c = ""
    loc = (job_location or "").strip()
    m = _HIRING_TITLE_RE.match(t)
    if m:
        if not c:
            c = m.group(1).strip()
        t = m.group(2).strip() or t
        if not loc:
            loc = m.group(3).strip()
    return (c or None, t or None, loc or None)
