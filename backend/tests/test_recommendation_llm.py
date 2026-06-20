"""LLM recommendation path (mocked)."""

from unittest.mock import patch

from app.schemas.candidate_profile import CandidateProfile, Constraints, Track
from app.schemas.report import JDParse, Recommendation, ResumeFitAnalysis
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
