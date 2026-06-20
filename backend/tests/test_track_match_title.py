"""Title resolution and Solutions Engineer track matching."""

from __future__ import annotations

from app.tools.profile_loader import get_candidate_profile
from app.tools.track_match import match_job_to_profile, resolve_job_title


def test_resolve_title_sniffs_solutions_engineer_from_jd_header() -> None:
    jd = "Solutions Engineer\nSalt AI\n\nAbout the job\nBuild prototypes with Python."
    assert resolve_job_title(None, jd) == "Solutions Engineer"


def test_solutions_engineer_maps_to_pm_eng_not_research() -> None:
    profile = get_candidate_profile()
    jd = (
        "About the job\nCollaborate with research scientists. "
        "Frontier AI research and publications preferred."
    )
    tm = match_job_to_profile("Solutions Engineer", jd, None, profile)
    track = tm["matched_track"]
    assert track is not None
    assert track.id == "pm_eng"
