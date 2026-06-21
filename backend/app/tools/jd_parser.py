"""parse_job_description — structured LLM extraction of a job description.

Turns raw JD text into typed requirements, each carrying a verbatim quote and a
citable evidence id (jd_req_01, …) so downstream analyses (resume fit, risk) can
reference them under the Report evidence contract (see docs/REPORT_SCHEMA.md).
"""

from __future__ import annotations

import re

from app.tools.llm import complete_json_with_retry, llm_available

_VALID_CATEGORIES = {
    "required_skill",
    "preferred_skill",
    "experience",
    "education",
    "responsibility",
    "location",
    "visa",
    "risk_keyword",
    "other",
}

_SYSTEM = (
    "You are a precise job-description parser. Extract only what is explicitly "
    "stated in the posting. Never invent requirements. Each requirement must "
    "include a short verbatim quote copied from the JD as evidence. "
    "Respond with a single JSON object and nothing else."
)

_SCHEMA_HINT = """Return JSON with exactly these keys:
{
  "location": string or null,           // work location / remote policy if stated
  "seniority": string or null,          // e.g. "Senior", "5-10 years", "Entry"
  "requirements": [
    {
      "category": one of ["required_skill","preferred_skill","experience","education","responsibility","location","visa","risk_keyword","other"],
      "text": string,                   // the requirement, concise
      "evidence_quote": string          // verbatim snippet from the JD supporting it
    }
  ],
  "visa_language": [string],            // phrases about sponsorship/visa, if any
  "risk_keywords": [string]             // vague/red-flag phrases, if any
}
Keep requirements focused (aim for the most important 5-15). Use [] when nothing applies."""


def _clean_str(v) -> str:
    return v.strip() if isinstance(v, str) else ""


_VISA_RE = re.compile(r"sponsorship|visa|h-1b|h1b|work authorization|authorized to work", re.I)
_SKILL_HINT = re.compile(
    r"\b(python|java|javascript|typescript|react|aws|sql|kubernetes|docker|"
    r"machine learning|llm|pytorch|tensorflow|c\+\+|go\b|rust\b|scala|"
    r"orchestrat|workflow|prototype|api\b|backend|frontend|data)\b",
    re.I,
)
_REQISH_HINT = re.compile(
    r"\b(required|must|minimum|qualification|proficiency|experience|years?|"
    r"responsible for|you will|you'll|ability to|preferred|bachelor|master|degree)\b",
    re.I,
)


def _categorize_fallback(line: str) -> str:
    low = line.lower()
    if _VISA_RE.search(line):
        return "visa"
    if re.search(r"\d+\+?\s*(years|yrs)\b", line, re.I):
        return "experience"
    if re.search(r"\b(bachelor|master|phd|degree|bs\b|ms\b)\b", line, re.I):
        return "education"
    if _SKILL_HINT.search(line):
        return "required_skill"
    if any(w in low for w in ("preferred", "nice to have", "plus")):
        return "preferred_skill"
    return "other"


def _build_parse_result(requirements: list[dict], visa_language: list[str], risk_keywords: list[str]) -> dict:
    evidence = []
    for req in requirements:
        evidence.append(
            {
                "id": req["id"],
                "type": "jd_requirement",
                "value": req["category"],
                "detail": req.get("evidence_quote") or req["text"],
            }
        )
    return {
        "available": True,
        "location": None,
        "seniority": None,
        "requirements": requirements,
        "visa_language": visa_language,
        "risk_keywords": risk_keywords,
        "evidence": evidence,
        "evidence_ids": [e["id"] for e in evidence],
    }


def _add_requirement(
    requirements: list[dict],
    seen: set[str],
    text: str,
    *,
    quote: str | None = None,
) -> None:
    # Strip an actual bullet/numbered-list marker, not meaningful leading
    # numbers such as "10+ years" or "8 years of supervisory experience".
    clean = re.sub(r"^\s*(?:[•\-*●▪]+\s*|\d+[.)]\s+)", "", text).strip()
    key = clean.lower()
    if len(clean) < 8 or key in seen:
        return
    seen.add(key)
    idx = len(requirements) + 1
    requirements.append(
        {
            "id": f"jd_req_{idx:02d}",
            "category": _categorize_fallback(clean),
            # Keep complete requirement sentences. Character slicing produced
            # user-visible half words such as "must hav" and "Federal, C".
            "text": clean,
            "evidence_quote": quote or clean,
        }
    )


def _fallback_parse(jd_text: str) -> dict | None:
    """Rule-based parse when LLM is down or returns garbage. Needs real JD text."""
    text = (jd_text or "").strip()
    if len(text) < 40:
        return None

    requirements: list[dict] = []
    seen: set[str] = set()
    visa_language: list[str] = []
    risk_keywords: list[str] = []

    # Normalize LinkedIn prose: split on bullets / numbered lists embedded in one line.
    normalized = re.sub(r"\s*([•●▪])\s*", r"\n\1 ", text)
    normalized = re.sub(r"\s+(\d+[.)]\s+)", r"\n\1", normalized)

    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if len(line) < 8 or len(line) > 320:
            continue
        is_bullet = bool(re.match(r"^[\s•\-\*●▪]+", line)) or bool(re.match(r"^\d+[.)]\s+", line))
        is_reqish = is_bullet or _REQISH_HINT.search(line) or _SKILL_HINT.search(line)
        if not is_reqish:
            if _VISA_RE.search(line) and line not in visa_language:
                visa_language.append(line[:200])
            continue
        _add_requirement(requirements, seen, line, quote=line)

    if len(requirements) < 3 and len(text) > 80:
        for sent in re.split(r"(?<=[.!?])\s+|[;\n]+", text):
            sent = sent.strip()
            if len(sent) < 16 or len(sent) > 240:
                continue
            if not (_REQISH_HINT.search(sent) or _SKILL_HINT.search(sent)):
                continue
            _add_requirement(requirements, seen, sent, quote=sent)
            if len(requirements) >= 12:
                break

    if not requirements:
        return None
    return _build_parse_result(requirements[:15], visa_language[:5], risk_keywords)


def _format_llm_result(data: dict) -> dict:
    requirements = []
    evidence = []
    for i, raw in enumerate(data.get("requirements") or [], start=1):
        if not isinstance(raw, dict):
            continue
        req_text = _clean_str(raw.get("text"))
        if not req_text:
            continue
        category = raw.get("category")
        if category not in _VALID_CATEGORIES:
            category = "other"
        rid = f"jd_req_{i:02d}"
        quote = _clean_str(raw.get("evidence_quote"))
        requirements.append(
            {"id": rid, "category": category, "text": req_text, "evidence_quote": quote}
        )
        evidence.append(
            {
                "id": rid,
                "type": "jd_requirement",
                "value": category,
                "detail": quote or req_text,
            }
        )

    visa_language = [s for s in (data.get("visa_language") or []) if isinstance(s, str)]
    risk_keywords = [s for s in (data.get("risk_keywords") or []) if isinstance(s, str)]

    return {
        "available": True,
        "location": data.get("location") or None,
        "seniority": data.get("seniority") or None,
        "requirements": requirements,
        "visa_language": visa_language,
        "risk_keywords": risk_keywords,
        "evidence": evidence,
        "evidence_ids": [e["id"] for e in evidence],
    }


def parse_job_description(
    jd_text: str,
    title: str | None = None,
    job_location: str | None = None,
) -> dict:
    """Parse a JD into the JDParse shape. Never raises; returns available=False on failure."""
    text = (jd_text or "").strip()
    if not text:
        return {"available": False, "reason": "no job description text provided"}

    def _with_location_hint(result: dict) -> dict:
        loc = (job_location or "").strip()
        if loc and not (result.get("location") or "").strip():
            result["location"] = loc
        return result

    if not llm_available():
        fb = _fallback_parse(text)
        if fb:
            return _with_location_hint(fb)
        return {"available": False, "reason": "LLM not configured (set LLM_API_KEY)"}

    # Fast path: structured LinkedIn JDs parse reliably without LLM (~0ms vs 30–90s).
    fb_quick = _fallback_parse(text)
    if fb_quick and len(fb_quick.get("requirements") or []) >= 2:
        return _with_location_hint(fb_quick)

    user_base = f"{_SCHEMA_HINT}\n\nJob title: {title or 'unknown'}\n\nJOB DESCRIPTION:\n"
    last_reason = "unknown error"
    data = None
    char_limits = (6000, 12000)
    for i, limit in enumerate(char_limits):
        user = user_base + text[:limit]
        try:
            data = complete_json_with_retry(
                _SYSTEM, user, max_attempts=1, base_delay_sec=0.5, max_tokens=2000
            )
            break
        except Exception as e:  # noqa: BLE001
            last_reason = str(e)
            data = None
    if data is None:
        fb = _fallback_parse(text)
        if fb:
            return _with_location_hint(fb)
        return {
            "available": False,
            "reason": (
                f"parse failed after retries: {last_reason}. "
                "Free LLM sometimes fails — click Analyze again."
            ),
        }

    result = _format_llm_result(data)
    if not result.get("requirements"):
        fb = _fallback_parse(text)
        if fb:
            return _with_location_hint(fb)
        return {
            "available": False,
            "reason": "no requirements extracted from JD — click Analyze again",
        }
    return _with_location_hint(result)

