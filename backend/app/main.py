from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.db import check_db_connection
from app.schemas.report import Report, SponsorshipAnalysis
from app.tools.entity_resolver import get_resolver
from app.tools.sponsorship import search_h1b_company


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


@app.get("/health")
def health() -> dict:
    db_ok = check_db_connection()
    return {
        "status": "ok",
        "database": "connected" if db_ok else "unavailable",
    }


@app.post("/analyze", response_model=Report)
def analyze(req: AnalyzeRequest) -> Report:
    """Partial analysis: real H-1B sponsorship lookup; the rest is pending.

    Returns the structured Report (see docs/REPORT_SCHEMA.md). JD parsing,
    resume fit, risk, and recommendation are added in later phases.
    """
    if req.company:
        sponsorship = SponsorshipAnalysis(**search_h1b_company(req.company))
    else:
        sponsorship = SponsorshipAnalysis(
            matched=False, reason="no company provided"
        )
    return Report(
        status="partial",
        pending=["jd_parsing", "resume_fit", "risk", "recommendation"],
        sponsorship=sponsorship,
        received={
            "company": req.company,
            "title": req.title,
            "jd_chars": len(req.jd_text),
            "has_resume": req.resume_text is not None,
            "job_url": req.job_url,
        },
    )
