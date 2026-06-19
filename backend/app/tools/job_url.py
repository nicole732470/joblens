"""Fetch and extract job posting text from a URL."""

from __future__ import annotations

import re

import httpx


def parse_job_url(url: str) -> dict:
    """Best-effort fetch. LinkedIn often blocks server-side fetch."""
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "reason": "invalid URL"}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; JobLens/1.0; +https://github.com/nicole732470/joblens)"
        ),
        "Accept": "text/html,application/xhtml+xml",
    }
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"fetch failed: {e}", "url": url}

    title = _meta(html, "og:title") or _title_tag(html) or ""
    company = _meta(html, "og:site_name") or ""
    text = _visible_text(html)
    text = re.sub(r"\s+", " ", text).strip()

    if "linkedin.com" in url.lower() and len(text) < 200:
        return {
            "ok": False,
            "reason": "LinkedIn blocks server fetch — use Chrome extension on the posting, or paste JD manually",
            "url": url,
            "title": title or None,
            "company": company or None,
        }

    if len(text) < 80:
        return {"ok": False, "reason": "could not extract enough job text from page", "url": url}

    return {
        "ok": True,
        "url": url,
        "title": title or None,
        "company": company or None,
        "jd_text": text[:12000],
    }


def _meta(html: str, prop: str) -> str:
    m = re.search(
        rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)',
        html,
        re.I,
    )
    return (m.group(1) if m else "").strip()


def _title_tag(html: str) -> str:
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    return (m.group(1) if m else "").strip()


def _visible_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<!--.*?-->", " ", html)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"\s+", " ", html)
    return html.strip()
