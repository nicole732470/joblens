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


def test_fallback_keeps_complete_requirement_text():
    requirement = (
        "Successful candidates must have a current PE registration and must have Healthcare "
        "design experience. In addition, a history of working with Healthcare, Federal, "
        "Critical Facilities, Commercial, and Aviation projects is preferred."
    )
    result = _fallback_parse(f"Job Requirements\n{requirement}\n10+ years experience required")
    assert result is not None
    claims = [row["text"] for row in result["requirements"]]
    assert requirement in claims
    assert all(not claim.endswith(("hav", "Federal, C", "Se")) for claim in claims)


def test_fallback_preserves_leading_experience_numbers():
    result = _fallback_parse(
        "Job Requirements\n10+ years of Project Management experience\n"
        "8 years of supervisory experience\n1. PE registration required"
    )
    assert result is not None
    claims = [row["text"] for row in result["requirements"]]
    assert "10+ years of Project Management experience" in claims
    assert "8 years of supervisory experience" in claims
    assert "PE registration required" in claims
