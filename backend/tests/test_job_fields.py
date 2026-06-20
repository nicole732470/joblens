from app.tools.job_fields import normalize_job_fields


def test_normalize_hiring_title_extracts_company():
    c, t, loc = normalize_job_fields(
        None,
        "Syska Hennessy Group hiring Technical Manager I in Dallas, TX",
        None,
    )
    assert c == "Syska Hennessy Group"
    assert "Technical Manager" in (t or "")
    assert loc == "Dallas, TX"


def test_normalize_keeps_explicit_company():
    c, t, _ = normalize_job_fields("Acme Inc", "Syska hiring Role in NYC", None)
    assert c == "Acme Inc"
    assert t == "Role"


def test_normalize_strips_linkedin_suffix():
    c, t, _ = normalize_job_fields(None, "Foo Corp hiring Bar in Boston | LinkedIn", None)
    assert c == "Foo Corp"
    assert t == "Bar"
