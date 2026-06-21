from app.schemas.candidate_profile import CandidateProfile, CompanyPreferences
from app.schemas.report import JDParse, SponsorshipAnalysis
from app.tools import company_signals


def _profile(**kwargs) -> CandidateProfile:
    return CandidateProfile(company_preferences=CompanyPreferences(**kwargs))


def test_company_weights_only_current_users_applicable_dimensions(monkeypatch):
    monkeypatch.setattr(
        company_signals,
        "research_company",
        lambda _name: {
            "available": True,
            "sources": [{"title": "Official", "url": "https://example.com", "content": "AI startup"}],
        },
    )
    monkeypatch.setattr(company_signals, "llm_available", lambda: True)
    monkeypatch.setattr(
        company_signals,
        "_llm_scores",
        lambda *_args: (
            {"industry": 0.8, "stage_funding": 0.6},
            {"industry": "AI", "stage_funding": "Series B"},
            [],
        ),
    )

    result = company_signals.score_company(
        "Example",
        JDParse(),
        "JD marketing must not be scored",
        _profile(industries=["AI"], stages=["growth"]),
        SponsorshipAnalysis(matched=False),
    )

    assert result["company_score"] == 0.7
    assert result["score_breakdown"]["effective_weight"] == 0.5
    assert result["score_breakdown"]["applicable"] == ["industry", "stage_funding"]


def test_unconfigured_dimension_is_not_zero(monkeypatch):
    monkeypatch.setattr(
        company_signals,
        "research_company",
        lambda _name: {
            "available": True,
            "sources": [{"title": "Official", "url": "https://example.com", "content": "AI company"}],
        },
    )
    monkeypatch.setattr(company_signals, "llm_available", lambda: True)
    monkeypatch.setattr(
        company_signals,
        "_llm_scores",
        lambda *_args: ({"industry": 0.8}, {"industry": "AI"}, []),
    )

    result = company_signals.score_company(
        "Example", JDParse(), "", _profile(industries=["AI"]), SponsorshipAnalysis(matched=False)
    )

    assert result["company_score"] == 0.8
    assert result["score_breakdown"]["confidence"] == "low"
    assert result["score_breakdown"]["effective_weight"] == 1.0


def test_company_does_not_use_jd_as_evidence(monkeypatch):
    monkeypatch.setattr(
        company_signals,
        "research_company",
        lambda _name: {"available": False, "reason": "Tavily not configured", "sources": []},
    )
    result = company_signals.score_company(
        "Example",
        JDParse(),
        "Perfect AI VC-backed company with Northwestern alumni",
        _profile(industries=["AI"]),
        SponsorshipAnalysis(matched=False),
    )
    assert result["available"] is False
    assert result["reason"] == "Tavily not configured"
