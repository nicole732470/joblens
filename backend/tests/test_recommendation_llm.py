"""LLM recommendation path (mocked)."""

from unittest.mock import patch

from app.schemas.candidate_profile import CandidateProfile, Constraints, Track
from app.schemas.report import Claim, JDParse, Recommendation, ResumeFitAnalysis
from app.tools.recommendation import generate_recommendation


def _profile() -> CandidateProfile:
    return CandidateProfile(
        tracks=[
            Track(id="ai_eng", label="AI Engineer", priority=1, example_titles=["AI Engineer"]),
        ],
        constraints=Constraints(),
    )


@patch("app.tools.recommendation_llm.llm_available", return_value=True)
@patch("app.tools.recommendation_llm.complete_json_with_retry")
def test_llm_recommendation_apply(mock_llm, _mock_avail):
    mock_llm.return_value = {
        "decision": "Apply",
        "reasoning": "Title matches AI Engineer track; resume shows agent and RAG work.",
        "summary": "AI Engineer · strong skill match",
        "track_id": "ai_eng",
        "track_label": "AI Engineer",
        "track_priority": 1,
        "location_tier": 2,
        "location_reason": "Austin is in configured tier-2 Texas",
    }
    jd = JDParse(
        available=True,
        requirements=[{"id": "jd_req_01", "text": "Build LLM agents", "category": "required_skill"}],
    )
    out = generate_recommendation(
        jd,
        ResumeFitAnalysis(available=False),
        _profile(),
        "AI Engineer",
        "We build production LLM agents.",
        resume_text="Built RAG pipeline and LangGraph agents at JobLens.",
        method="llm",
    )
    assert out["available"] is True
    assert out["decision"] == Recommendation.APPLY
    assert out["recommendation_method"] == "llm"
    assert "agent" in out["reasoning"].lower()
    assert out["location_tier"] == 2
    assert "Texas" in out["location_label"]


@patch("app.tools.recommendation_llm.llm_available", return_value=True)
@patch("app.tools.recommendation_llm.complete_json_with_retry")
def test_llm_skip_summary_not_generic(mock_llm, _mock_avail):
    mock_llm.return_value = {
        "decision": "Skip",
        "reasoning": "JD is a research scientist role requiring PhD publications; resume is product AI engineering.",
        "summary": "not a strong fit",
        "track_id": "research",
        "track_label": "Research Scientist",
        "track_priority": 5,
    }
    jd = JDParse(available=True, requirements=[])
    out = generate_recommendation(
        jd,
        ResumeFitAnalysis(available=False),
        _profile(),
        "Research Scientist",
        "PhD required. Publish in top venues.",
        resume_text="Shipped RAG products.",
        method="llm",
    )
    assert out["decision"] == Recommendation.SKIP
    assert out["summary"].lower() != "not a strong fit"
    assert len(out["summary"]) >= 12


@patch("app.tools.recommendation_llm.llm_available", return_value=True)
@patch("app.tools.recommendation_llm.complete_json_with_retry")
def test_p1_role_and_resume_over_50_forces_apply(mock_llm, _mock_avail):
    mock_llm.return_value = {
        "decision": "Consider",
        "reasoning": "Model was uncertain.",
        "summary": "Mixed fit",
        "track_id": "ai_eng",
        "track_label": "AI Engineer",
        "track_priority": 3,
        "preference_hits": [],
        "dealbreaker_hits": [],
    }
    fit = ResumeFitAnalysis(
        available=True,
        strong_matches=[Claim(claim="a", claim_type="resume_fit")] * 2,
        partial_matches=[Claim(claim="b", claim_type="resume_fit")],
        missing=[Claim(claim="c", claim_type="resume_fit")],
    )
    jd = JDParse(available=True, requirements=[])
    out = generate_recommendation(
        jd,
        fit,
        _profile(),
        "AI Engineer",
        "Build AI agents.",
        resume_text="Built production AI agents and RAG systems.",
        method="llm",
    )
    assert out["decision"] == Recommendation.APPLY
    assert out["track_priority"] == 1


@patch("app.tools.recommendation_llm.llm_available", return_value=True)
@patch("app.tools.recommendation_llm.complete_json_with_retry")
def test_ai_dealbreaker_hit_forces_skip(mock_llm, _mock_avail):
    profile = _profile().model_copy(update={"dealbreakers": ["unpaid internship"]})
    mock_llm.return_value = {
        "decision": "Apply",
        "reasoning": "Otherwise aligned.",
        "summary": "Strong fit",
        "track_id": "ai_eng",
        "dealbreaker_hits": ["unpaid internship", "invented rule"],
        "preference_hits": [],
    }
    out = generate_recommendation(
        JDParse(available=True, requirements=[]),
        ResumeFitAnalysis(available=False),
        profile,
        "AI Engineer Intern",
        "This is an unpaid internship.",
        resume_text="Built AI systems.",
        method="llm",
    )
    assert out["decision"] == Recommendation.SKIP
    assert out["dealbreaker_hits"] == ["unpaid internship"]
