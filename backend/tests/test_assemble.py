"""Assemble Report from analysis artifacts."""

from app.schemas.report import Recommendation
from app.tools.analysis_context import begin_analysis, set_artifact
from app.tools.observability import start_trace
from app.graph.assemble import assemble_report


def _explain(rec, co):
    return {"role": {}, "company": {}, "flags": {}}


def test_assemble_from_artifacts():
    start_trace()
    begin_analysis(
        {
            "jd_text": "Need Python",
            "company": "Acme",
            "title": "Engineer",
            "resolved_resume": "resume body",
            "resume_source": "default",
        }
    )
    set_artifact("sponsorship", {"matched": False})
    set_artifact("jd", {"available": True, "requirements": []})
    set_artifact(
        "resume_fit",
        {
            "available": True,
            "match_method": "llm",
            "strong_matches": [],
            "partial_matches": [],
            "missing": [],
        },
    )
    set_artifact(
        "recommendation",
        {
            "available": True,
            "decision": Recommendation.SKIP,
            "reasoning": "test",
        },
    )
    set_artifact("company_analysis", {"available": True, "company_tier": 2})
    set_artifact("risk", {"available": True, "risks": []})

    report = assemble_report(build_explain=_explain, observability={"run_id": "test"})
    assert report.resume_fit.match_method == "llm"
    assert report.status in ("complete", "partial")
