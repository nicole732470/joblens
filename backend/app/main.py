from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.db import check_db_connection
from app.schemas.candidate_profile import CandidateProfile
from app.schemas.report import (
    CompanyAnalysis,
    JDParse,
    Report,
    RecommendationResult,
    ResumeFitAnalysis,
    RiskAnalysis,
    SponsorshipAnalysis,
)
from app.tools.company_signals import score_company
from app.tools.entity_resolver import get_resolver
from app.tools.jd_parser import parse_job_description
from app.tools.profile_loader import get_candidate_profile
from app.tools.recommendation import generate_recommendation
from app.tools.resume_fit import analyze_resume_fit
from app.tools.resume_loader import resolve_resume_text
from app.tools.resume_store import index_resume
from app.tools.risk_rules import run_risk_rules
from app.tools.sponsorship import search_h1b_company


def _build_explain(
    recommendation: RecommendationResult,
    company: CompanyAnalysis,
) -> dict:
    rec = recommendation
    co = company
    return {
        "flags": {
            "count": rec.dealbreakers_matched,
            "hits": rec.dealbreaker_hits,
            "note": "JD text matched your dealbreakers (hard veto list in profile YAML).",
        },
        "company": {
            "tier": co.company_tier,
            "label": co.company_label,
            "score": co.company_score,
            "dealbreaker_hits": co.dealbreaker_hits,
            "preference_hits": co.preference_hits,
            "breakdown": co.score_breakdown,
            "note": (
                "P3 from dealbreaker if listed; otherwise combined score "
                "(≥0.52 P1, ≥0.38 P2, else P3). Not H-1B sponsor odds."
            ),
        },
        "role": {
            "track": rec.track_label,
            "priority": rec.track_priority,
            "similarity": rec.track_similarity,
            "fit_ratio": rec.fit_ratio,
            "adjustments": rec.technical_penalty_hits,
        },
        "debug": "DevTools → Network → POST /analyze → Response JSON → explain",
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm the in-memory entity-resolution index so the first /analyze is fast.
    try:
        get_resolver()
    except Exception:
        pass
    yield


app = FastAPI(title="Job Intelligence API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/response models live here for the skeleton; they will move into
# app/schemas/ once the full report contract is defined (see docs/DESIGN.md).
class AnalyzeRequest(BaseModel):
    jd_text: str
    company: str | None = None
    title: str | None = None
    resume_text: str | None = None
    job_url: str | None = None
    linkedin_followers: int | None = None
    alumni_hints: list[str] = []


class IndexResumeRequest(BaseModel):
    resume_text: str
    resume_key: str | None = None


@app.get("/health")
def health() -> dict:
    db_ok = check_db_connection()
    profile_ok = False
    try:
        get_candidate_profile()
        profile_ok = True
    except Exception:
        pass
    return {
        "status": "ok",
        "database": "connected" if db_ok else "unavailable",
        "candidate_profile": "loaded" if profile_ok else "unavailable",
    }


@app.get("/candidate-profile", response_model=CandidateProfile)
def candidate_profile() -> CandidateProfile:
    """Return the loaded candidate intent profile (for debugging / extension)."""
    return get_candidate_profile()


@app.post("/resume/index")
def resume_index(req: IndexResumeRequest) -> dict:
    """Chunk, embed, and store resume text in pgvector."""
    try:
        return index_resume(req.resume_text, req.resume_key)
    except Exception as e:  # noqa: BLE001
        return {"indexed": False, "reason": str(e)}


@app.post("/analyze", response_model=Report)
def analyze(req: AnalyzeRequest) -> Report:
    """Partial analysis: H-1B sponsorship lookup + JD parsing + resume fit."""
    if req.company:
        sponsorship = SponsorshipAnalysis(**search_h1b_company(req.company))
    else:
        sponsorship = SponsorshipAnalysis(
            matched=False, reason="no company provided"
        )

    jd = JDParse(**parse_job_description(req.jd_text, req.title))

    resume_text, resume_source = resolve_resume_text(req.resume_text)

    resume_fit = ResumeFitAnalysis()
    if resume_text:
        try:
            resume_fit = ResumeFitAnalysis(**analyze_resume_fit(jd, resume_text))
        except Exception as e:  # noqa: BLE001
            resume_fit = ResumeFitAnalysis(available=False, reason=str(e))

    try:
        profile = get_candidate_profile()
    except Exception:
        profile = None

    risk = RiskAnalysis()
    company = CompanyAnalysis()
    recommendation = RecommendationResult()
    if profile is not None:
        try:
            company = CompanyAnalysis(
                **score_company(
                    req.company,
                    jd,
                    req.jd_text,
                    profile,
                    sponsorship,
                    linkedin_followers=req.linkedin_followers,
                    alumni_hints=req.alumni_hints or None,
                )
            )
        except Exception as e:  # noqa: BLE001
            company = CompanyAnalysis(available=False, reason=str(e))
        try:
            risk = RiskAnalysis(**run_risk_rules(jd, resume_fit, profile))
        except Exception as e:  # noqa: BLE001
            risk = RiskAnalysis(available=False, reason=str(e))
        try:
            recommendation = RecommendationResult(
                **generate_recommendation(jd, resume_fit, profile, req.title, req.jd_text)
            )
        except Exception as e:  # noqa: BLE001
            recommendation = RecommendationResult(available=False, reason=str(e))

    pending: list[str] = []
    if not jd.available:
        pending.append("jd_parsing")
    if not resume_text:
        pending.append("resume_fit")
    elif not resume_fit.available:
        pending.append("resume_fit")
    if profile is None:
        pending.append("recommendation")
    elif not recommendation.available:
        pending.append("recommendation")

    status = "complete" if not pending else "partial"

    explain = _build_explain(recommendation, company) if profile is not None else {}

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
            "company": req.company,
            "title": req.title,
            "jd_chars": len(req.jd_text),
            "has_resume": resume_text is not None,
            "resume_source": resume_source,
            "job_url": req.job_url,
            "linkedin_followers": req.linkedin_followers,
            "alumni_hints": req.alumni_hints,
        },
        explain=explain,
    )
