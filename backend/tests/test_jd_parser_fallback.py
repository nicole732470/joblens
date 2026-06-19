"""JD parser fallback for LinkedIn-style prose."""

from app.tools.jd_parser import parse_job_description, _fallback_parse


SALT_AI_SNIPPET = """
Solutions Engineer
Salt AI · San Francisco, CA

About the job
Build functional workflow prototypes using Salt's orchestration platform.
3+ years experience with Python required. Must collaborate with cross-functional teams.
Experience with AWS and Kubernetes preferred. Bachelor's degree in CS or related field.
"""


def test_fallback_extracts_salt_ai_requirements():
    result = _fallback_parse(SALT_AI_SNIPPET)
    assert result is not None
    assert len(result["requirements"]) >= 2


def test_parse_uses_fallback_when_llm_returns_empty(monkeypatch):
    monkeypatch.setattr(
        "app.tools.jd_parser.complete_json_with_retry",
        lambda *a, **k: {"requirements": [], "visa_language": [], "risk_keywords": []},
    )
    monkeypatch.setattr("app.tools.jd_parser.llm_available", lambda: True)
    result = parse_job_description(SALT_AI_SNIPPET, "Solutions Engineer")
    assert result.get("available") is True
    assert len(result.get("requirements") or []) >= 2
