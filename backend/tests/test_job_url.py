"""Job URL validation — reject non-job pages."""

from app.tools.job_url import _linkedin_description, is_likely_job_url, looks_like_job_posting


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


def test_accepts_linkedin_extension_scrape():
    """Extension sends long in-browser JD + linkedin job URL — do not false-reject."""
    text = (
        "Technical Manager I will provide review and control over engineering projects. "
        "Successful candidates must have a current PE registration and healthcare design experience. "
        "Bachelor's degree in Electrical engineering. 10+ years in a consulting firm."
    )
    url = "https://www.linkedin.com/jobs/view/4306005860/?currentJobId=4306005860"
    ok, reason = looks_like_job_posting(text, "Technical Manager I", url)
    assert ok, reason


def test_extracts_only_linkedin_job_description():
    html = """
    <html><body>
      <div>Sign in to access AI-powered advice</div>
      <section class="show-more-less-html">
        <div class="show-more-less-html__markup show-more-less-html__markup--clamp-after-5">
          Build landmark projects.<br><br><strong>Job Requirements</strong>
          <ul><li>PE registration required</li><li>12+ years of experience</li></ul>
        </div>
      </section>
      <section><h2>Similar jobs</h2><div>Unrelated software engineer role</div></section>
    </body></html>
    """
    text = _linkedin_description(html)
    assert "Build landmark projects" in text
    assert "PE registration required" in text
    assert "12+ years of experience" in text
    assert "Sign in" not in text
    assert "Similar jobs" not in text
    assert "PE registration required\n12+ years of experience" in text


def test_linkedin_description_decodes_entities():
    html = '<div class="show-more-less-html__markup">R&amp;D &mdash; 10+ years</div>'
    assert _linkedin_description(html) == "R&D — 10+ years"

