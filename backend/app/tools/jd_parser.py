"""parse_job_description — structured LLM extraction of a job description.

Turns raw JD text into typed requirements, each carrying a verbatim quote and a
citable evidence id (jd_req_01, …) so downstream analyses (resume fit, risk) can
reference them under the citation contract (see docs/DESIGN.md §7-8).
"""

from __future__ import annotations

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


def parse_job_description(jd_text: str, title: str | None = None) -> dict:
    """Parse a JD into the JDParse shape. Never raises; returns available=False on failure."""
    text = (jd_text or "").strip()
    if not text:
        return {"available": False, "reason": "no job description text provided"}
    if not llm_available():
        return {"available": False, "reason": "LLM not configured (set LLM_API_KEY)"}

    user = f"{_SCHEMA_HINT}\n\nJob title: {title or 'unknown'}\n\nJOB DESCRIPTION:\n{text[:12000]}"
    try:
        data = complete_json_with_retry(_SYSTEM, user, max_attempts=3, base_delay_sec=0.8)
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"parse failed after 3 attempts: {e}"}

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
