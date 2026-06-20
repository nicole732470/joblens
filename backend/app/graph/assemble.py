"""Assemble Report from analysis artifacts + request input."""

from __future__ import annotations

from app.schemas.report import (
    CompanyAnalysis,
    JDParse,
    RecommendationResult,
    Report,
    ResumeFitAnalysis,
    RiskAnalysis,
    SponsorshipAnalysis,
)
from app.tools.analysis_context import get_artifacts, get_input
from app.tools.resume_summary import resume_summary


def assemble_report(
    *,
    build_explain,
    agent_meta: dict | None = None,
    observability: dict | None = None,
) -> Report:
    artifacts = get_artifacts()
    req = get_input()

    sponsorship = SponsorshipAnalysis(**(artifacts.get("sponsorship") or {"matched": False}))
    jd = JDParse(**(artifacts.get("jd") or {"available": False, "reason": "not parsed"}))
    resume_fit = ResumeFitAnalysis(**(artifacts.get("resume_fit") or {}))
    company = CompanyAnalysis(**(artifacts.get("company_analysis") or {}))
    risk = RiskAnalysis(**(artifacts.get("risk") or {}))
    recommendation = RecommendationResult(**(artifacts.get("recommendation") or {}))

    pending: list[str] = []
    if not jd.available:
        pending.append("jd_parsing")
    if not req.get("resolved_resume"):
        pending.append("resume_fit")
    elif not resume_fit.available:
        pending.append("resume_fit")
    if not recommendation.available:
        pending.append("recommendation")

    status = "complete" if not pending else "partial"
    explain = build_explain(recommendation, company) if recommendation.available or company.available else {}
    explain = {
        **explain,
        "resume_fit": {
            "match_method": resume_fit.match_method,
            "note": (
                "llm = embeddings retrieve evidence, then LLM judges each requirement; "
                "vector = distance thresholds only."
            ),
        },
        "agent": agent_meta or {},
        "observability": observability or {},
    }

    resolved = req.get("resolved_resume") or ""
    return Report(
        status=status,
        pending=pending,
        sponsorship=sponsorship,
        company=company,
        jd=jd,
        resume_fit=resume_fit,
        risk=risk,
        recommendation=recommendation,
        received={
            "company": req.get("company"),
            "title": req.get("title"),
            "jd_chars": len(req.get("jd_text") or ""),
            "has_resume": bool(resolved),
            "resume_chars": len(resolved),
            "resume_summary": resume_summary(resolved),
            "resume_filename": req.get("resume_filename"),
            "resume_source": req.get("resume_source"),
            "job_url": req.get("job_url"),
            "job_location": req.get("job_location"),
            "linkedin_followers": req.get("linkedin_followers"),
            "alumni_hints": req.get("alumni_hints"),
        },
        explain=explain,
    )
