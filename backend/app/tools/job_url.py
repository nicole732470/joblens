"""Fetch and extract job posting text from a URL — with job-page validation."""

from __future__ import annotations

import re

import httpx

from app.tools.job_fields import normalize_job_fields

# Known job-board URL patterns (not exhaustive — paired with content heuristics).
_JOB_URL_HINTS = re.compile(
    r"(?:"
    r"linkedin\.com/jobs/view/|currentJobId=|"
    r"boards\.greenhouse\.io|greenhouse\.io/.+/jobs/|"
    r"jobs\.lever\.co|lever\.co/.+/|"
    r"ashbyhq\.com/.+/|"
    r"myworkdayjobs\.com|workday\.com/.+/job/|"
    r"smartrecruiters\.com|icims\.com|jobvite\.com|"
    r"careers\.[^/]+|/careers/|/jobs/view/|/jobs/\d|/job/\d|"
    r"apply\.workable\.com|jobs\.db\.com"
    r")",
    re.I,
)

_NON_JOB_URL = re.compile(
    r"(?:"
    r"linkedin\.com/(?:feed|in/|company/|posts/|pulse/|learning/|mynetwork/)|"
    r"linkedin\.com/?$|"
    r"google\.com|youtube\.com|twitter\.com|x\.com|facebook\.com|"
    r"github\.com/(?!.*/jobs)"
    r")",
    re.I,
)

_JOB_CONTENT_SIGNALS = (
    "responsibilities",
    "qualifications",
    "requirements",
    "job description",
    "what you'll do",
    "what you will do",
    "we are looking",
    "we're looking",
    "you will",
    "you'll",
    "experience required",
    "years of experience",
    "bachelor",
    "master's",
    "apply now",
    "equal opportunity",
    "benefits",
    "salary",
    "full-time",
    "full time",
)


def is_likely_job_url(url: str) -> tuple[bool, str]:
    """Fast URL-shape check before fetch."""
    u = (url or "").strip().lower()
    if not u.startswith(("http://", "https://")):
        return False, "invalid URL — must start with http:// or https://"
    if _NON_JOB_URL.search(u):
        return False, "this URL is not a job posting (LinkedIn feed, profile, or generic site)"
    if "linkedin.com" in u and not re.search(r"linkedin\.com/jobs/|currentJobId=", u):
        return False, "LinkedIn URL must be a job posting (/jobs/view/… or ?currentJobId=) — use the extension on LinkedIn or paste the JD"
    if _JOB_URL_HINTS.search(u):
        return True, ""
    # Allow unknown hosts only if path smells like a job page.
    if re.search(r"/(jobs?|careers|positions|openings)/", u):
        return True, ""
    return False, "URL does not look like a job posting — paste a careers/jobs link or the JD text manually"


def looks_like_job_posting(
    text: str, title: str = "", job_url: str | None = None
) -> tuple[bool, str]:
    """Content heuristic after fetch."""
    body = (text or "").strip()
    blob = f"{title}\n{body}".lower()
    if len(blob.strip()) < 80:
        return False, "extracted text too short to be a job description"

    u = (job_url or "").lower()
    # Extension scrapes LinkedIn in-browser — long text on a job URL is trusted.
    if len(body) >= 180 and (
        re.search(r"linkedin\.com/jobs/|currentJobId=", u)
        or _JOB_URL_HINTS.search(u)
    ):
        return True, ""

    hits = sum(1 for s in _JOB_CONTENT_SIGNALS if s in blob)
    if hits >= 2:
        return True, ""
    if hits >= 1 and len(body) >= 400:
        return True, ""
    # Single strong signal
    if any(x in blob for x in ("job description", "responsibilities", "qualifications")):
        return True, ""
    extra_signals = (
        "job requirements",
        "minimum qualifications",
        "must have",
        "years of experience",
        "years'",
        "preferred qualifications",
        "what you'll do",
        "about the role",
        "about this role",
        "key responsibilities",
    )
    if any(x in blob for x in extra_signals) and len(body) >= 120:
        return True, ""
    return False, "page content does not look like a job description — paste the JD manually or use a direct job link"


def parse_job_url(url: str) -> dict:
    """Best-effort fetch. LinkedIn often blocks server-side fetch."""
    url = (url or "").strip()
    ok_url, url_reason = is_likely_job_url(url)
    if not ok_url:
        return {"ok": False, "reason": url_reason, "url": url}

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
    company, title, job_location = normalize_job_fields(company, title, None)
    text = _visible_text(html)
    text = re.sub(r"\s+", " ", text).strip()

    if "linkedin.com" in url.lower() and len(text) < 200:
        return {
            "ok": False,
            "reason": "LinkedIn blocks server fetch — use Chrome extension on the posting, or paste JD manually",
            "url": url,
            "title": title or None,
            "company": company or None,
            "job_location": job_location,
            "jd_text": text[:12000] if len(text.strip()) >= 40 else None,
        }

    if len(text.strip()) < 40:
        return {
            "ok": False,
            "reason": "extracted text too short",
            "url": url,
            "title": title or None,
            "company": company or None,
        }

    return {
        "ok": True,
        "url": url,
        "title": title or None,
        "company": company or None,
        "job_location": job_location,
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
