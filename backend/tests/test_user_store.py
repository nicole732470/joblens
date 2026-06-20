"""User profile merges YAML defaults for empty web onboarding fields."""

from app.schemas.candidate_profile import CandidateProfile, Locations, Track
from app.user_store import merge_profile_with_yaml_defaults


def test_merge_fills_empty_tier_1_from_yaml():
    user = CandidateProfile(
        tracks=[Track(id="x", label="AI Engineer", priority=1, example_titles=["AI Engineer"])],
        locations=Locations(tier_1=[], tier_2=[], tier_3=[], remote_ok=True),
    )
    merged = merge_profile_with_yaml_defaults(user)
    assert merged.locations.tier_1
    assert any("chicago" in p.lower() for p in merged.locations.tier_1)
