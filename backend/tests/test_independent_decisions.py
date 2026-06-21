import json
from unittest.mock import patch

from app.schemas.candidate_profile import CandidateProfile, Track
from app.schemas.report import JDParse
from app.tools.independent_decisions import decide_role
from app.tools.track_match import match_role_content_to_profile


def _profile():
    return CandidateProfile(
        tracks=[Track(id="ai_eng", label="AI Engineer", priority=1, example_titles=["AI Engineer"])]
    )


@patch("app.tools.independent_decisions.match_role_content_to_profile")
@patch("app.tools.independent_decisions.complete_json_with_retry")
def test_low_similarity_role_fallback_stays_unmatched(mock_llm, mock_match):
    mock_llm.side_effect = json.JSONDecodeError("bad JSON", "{broken", 1)
    mock_match.return_value = {
        "matched_track": _profile().tracks[0],
        "similarity": 0.448,
        "avoid_match": False,
        "avoid_label": None,
    }
    result = decide_role(
        "Technical Manager I (Electrical Engineer)",
        "Electrical and architectural engineering consulting role.",
        JDParse(available=True),
        _profile(),
    )
    validated = result["validated_output"]
    assert result["method"] == "embedding/rules"
    assert validated["track_id"] is None
    assert validated["track_priority"] == 4
    assert validated["role_status"] == "unmatched"


@patch("app.tools.independent_decisions.match_role_content_to_profile")
@patch("app.tools.independent_decisions.complete_json_with_retry")
def test_high_similarity_role_fallback_can_select_target(mock_llm, mock_match):
    profile = _profile()
    mock_llm.side_effect = RuntimeError("model unavailable")
    mock_match.return_value = {
        "matched_track": profile.tracks[0],
        "similarity": 0.72,
        "avoid_match": False,
        "avoid_label": None,
    }
    result = decide_role("AI Engineer", "Build AI agents", JDParse(available=True), profile)
    assert result["validated_output"]["track_id"] == "ai_eng"
    assert result["validated_output"]["role_status"] == "target"


@patch("app.tools.independent_decisions.match_role_content_to_profile")
@patch("app.tools.independent_decisions.complete_json_with_retry")
def test_llm_ai_selection_is_rejected_for_electrical_role_without_ai_work(mock_llm, mock_match):
    profile = _profile()
    mock_llm.return_value = {
        "track_id": "ai_eng",
        "avoid_track_id": None,
        "reason": "incorrect nearest category",
        "evidence": ["Electrical Engineer"],
    }
    mock_match.return_value = {
        "matched_track": profile.tracks[0],
        "similarity": 0.448,
        "avoid_match": False,
        "avoid_label": None,
    }
    result = decide_role(
        "Technical Manager I (Electrical Engineer)",
        "Lead electrical design and PE consulting projects.",
        JDParse(available=True),
        profile,
    )
    assert result["method"] == "embedding/rules"
    assert result["validated_output"]["role_status"] == "unmatched"
    assert "contradicts" in result["validation_error"]


@patch("app.tools.track_match.embed_texts")
def test_role_embedding_fallback_includes_jd_responsibilities(mock_embed):
    captured = []

    def fake_embed(texts):
        captured.extend(texts)
        return [[1.0, 0.0], [0.0, 1.0]]

    mock_embed.side_effect = fake_embed
    jd = JDParse(
        available=True,
        requirements=[
            {
                "id": "jd_req_01",
                "category": "responsibility",
                "text": "Lead MEP electrical design and PE quality assurance",
            }
        ],
    )
    result = match_role_content_to_profile(
        "Technical Manager I",
        "Electrical engineering consulting",
        jd,
        _profile(),
    )
    assert "Lead MEP electrical design" in captured[0]
    assert result["matched_track"] is None
