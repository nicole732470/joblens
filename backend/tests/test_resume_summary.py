from app.tools.resume_summary import resume_summary


def test_resume_summary_skips_markdown_headers():
    text = "# Nicole Li\n\n## Technical PM | Tencent\nBuilt AI pipelines."
    out = resume_summary(text)
    assert "Nicole" in out or "Built AI" in out
    assert "##" not in out
