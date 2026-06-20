"""Job URL validation — reject non-job pages."""

from app.tools.job_url import is_likely_job_url, looks_like_job_posting


def test_rejects_linkedin_feed():
    ok, reason = is_likely_job_url("https://www.linkedin.com/feed/")
    assert not ok
    assert "not a job" in reason.lower()


def test_rejects_linkedin_profile():
    ok, _ = is_likely_job_url("https://www.linkedin.com/in/someone/")
    assert not ok


def test_accepts_linkedin_job_view():
    ok, reason = is_likely_job_url(
        "https://www.linkedin.com/jobs/view/4306005860/?alternateChannel=search"
    )
    assert ok
    assert reason == ""


def test_accepts_greenhouse():
    ok, _ = is_likely_job_url("https://boards.greenhouse.io/acme/jobs/12345")
    assert ok


def test_rejects_random_site():
    ok, reason = is_likely_job_url("https://www.google.com/search?q=jobs")
    assert not ok
    assert "not a job" in reason.lower()


def test_looks_like_job_posting_minimal_jd():
    text = (
        "Responsibilities: build APIs. Qualifications: 3 years Python. "
        "We are looking for a strong engineer. Bachelor's required."
    )
    ok, _ = looks_like_job_posting(text, "Software Engineer")
    assert ok


def test_rejects_short_non_job_text():
    ok, reason = looks_like_job_posting("Welcome to our homepage. About us.", "Home")
    assert not ok
    assert "job" in reason.lower()
