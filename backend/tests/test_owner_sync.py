"""Owner account golden sync."""

from unittest.mock import patch

import pytest

from app.schemas.candidate_profile import CandidateProfile, Locations
from app.user_store import is_owner_email, merge_profile_with_yaml_defaults


def test_is_owner_email():
    assert is_owner_email("nicole732470@gmail.com")
    assert not is_owner_email("other@example.com")


def test_merge_fills_technical_penalties_from_yaml():
    user = CandidateProfile(
        tracks=[],
        locations=Locations(tier_1=["Chicago"]),
        technical_penalties=[],
        alumni_schools=[],
    )
    base = CandidateProfile(
        technical_penalties=["mechanical engineering"],
        alumni_schools=["Northwestern"],
    )
    with patch("app.user_store._yaml_default_profile", return_value=base):
        merged = merge_profile_with_yaml_defaults(user)
    assert "mechanical engineering" in merged.technical_penalties
    assert "Northwestern" in merged.alumni_schools
