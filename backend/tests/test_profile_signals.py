"""Location / onsite detection — regression tests."""

from app.schemas.candidate_profile import CandidateProfile, Locations
from app.schemas.report import JDParse
from app.tools.profile_signals import (
    _is_fully_remote_job,
    _is_onsite_job,
    _mentions_remote_policy,
    score_location,
)


def _profile(**kwargs) -> CandidateProfile:
    defaults = {
        "tracks": [],
        "locations": Locations(
            tier_1=["Chicago"],
            tier_2=["Texas", "California", "New York"],
            tier_3=["rural"],
            remote_ok=True,
        ),
    }
    defaults.update(kwargs)
    return CandidateProfile(**defaults)


def test_onsite_one_word_in_linkedin_title():
    title = "(Part-time/Onsite - Clearwater, FL)"
    assert _is_onsite_job(title)
    assert not _mentions_remote_policy(title)


def test_clearwater_onsite_not_remote():
    title = "Software Engineer (Part-time/Onsite - Clearwater, FL)"
    jd = JDParse(available=False)
    loc = score_location(jd, "Must work from our Clearwater office.", _profile(), title)
    assert loc["location_tier"] == 4
    assert "Remote" not in (loc["location_label"] or "")
    assert "Clearwater" in (loc["location_label"] or "")


def test_fully_remote_is_p1():
    jd = JDParse(available=True, location="Fully remote within the US")
    loc = score_location(jd, "This role is fully remote.", _profile())
    assert loc["location_tier"] == 1
    assert "Fully remote" in (loc["location_label"] or "")


def test_remote_location_is_p1():
    loc = score_location(
        JDParse(available=False),
        "Build production systems.",
        _profile(),
        job_location="Remote",
    )
    assert loc["location_tier"] == 1


def test_fully_remote_beats_geographic_tier():
    jd = JDParse(available=True, location="Austin, TX — fully remote")
    loc = score_location(
        jd,
        "This is a fully remote role available throughout the US.",
        _profile(),
        job_location="Austin, TX · Remote",
    )
    assert loc["location_tier"] == 1
    assert "Fully remote" in (loc["location_label"] or "")


def test_hybrid_uses_geographic_tier():
    jd = JDParse(available=True, location="Austin, TX (Hybrid)")
    loc = score_location(
        jd,
        "Hybrid role with three days per week in the Austin office.",
        _profile(),
        job_location="Austin, TX · Hybrid",
    )
    assert not _is_fully_remote_job("Hybrid role with remote flexibility")
    assert loc["location_tier"] == 2
    assert "Texas" in (loc["location_label"] or "")


def test_chicago_jd_location_is_p1():
    jd = JDParse(available=True, location="Chicago, IL")
    loc = score_location(jd, "Join our downtown Chicago office.", _profile())
    assert loc["location_tier"] == 1
    assert "Chicago" in (loc["location_label"] or "")


def test_chicago_in_title_is_p1():
    title = "Software Engineer (Chicago, IL)"
    jd = JDParse(available=False)
    loc = score_location(jd, "Build production systems.", _profile(), title)
    assert loc["location_tier"] == 1
    assert "P1" in (loc["location_label"] or "")


def test_chicago_in_full_jd_when_hq_elsewhere():
    jd = JDParse(available=True, location="Chicago, IL")
    text = (
        "HQ: San Francisco. This role is based in Chicago, IL. "
        "Responsibilities include building APIs."
    )
    loc = score_location(jd, text, _profile())
    assert loc["location_tier"] == 1
    assert "Chicago" in (loc["location_label"] or "")


def test_chicago_linkedin_location_line_only():
    """City under the title (not in title) should still score P1."""
    jd = JDParse(available=False)
    loc = score_location(
        jd,
        "HQ: San Francisco. Remote workers welcome.",
        _profile(),
        "Software Engineer",
        "Chicago, IL · On-site",
    )
    assert loc["location_tier"] == 1
    assert "Chicago" in (loc["location_label"] or "")
