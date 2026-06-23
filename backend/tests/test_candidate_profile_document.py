from pathlib import Path

from app.schemas.candidate_profile import CandidateProfile, CandidateProfileDocument
from app.tools.profile_loader import load_candidate_profile, load_candidate_profile_document


PROFILE_PATH = Path(__file__).resolve().parents[2] / "evals/golden_set/candidate_profile.yaml"


def test_internal_document_fields_do_not_enter_public_profile() -> None:
    document = load_candidate_profile_document(PROFILE_PATH)
    public = document.public_profile()

    assert isinstance(document, CandidateProfileDocument)
    assert isinstance(public, CandidateProfile)
    assert document.profile_status == "draft"
    assert document.seniority_policy.maximum_level == "senior"
    assert "profile_status" not in public.model_dump()
    assert "learning_policy" not in public.model_dump()
    assert "open_questions" not in public.model_dump()
    assert "seniority_policy" not in public.model_dump()
    assert "technical_scope" not in public.model_dump()


def test_default_loader_preserves_existing_public_user_format() -> None:
    public = load_candidate_profile(PROFILE_PATH)
    fields = set(public.model_dump())

    assert fields == {
        "tracks", "avoid_tracks", "locations", "dealbreakers", "preferences",
        "company_preferences", "technical_penalties", "alumni_schools", "constraints",
    }
