from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.db import check_db_connection

app = FastAPI(title="Job Intelligence API", version="0.1.0")

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


@app.post("/analyze")
def analyze(req: AnalyzeRequest) -> dict:
    """Stub. Returns a placeholder report so the end-to-end path is wired.

    Real analysis (JD parsing, H-1B lookup, resume fit, risk, recommendation)
    is added in later phases per docs/DESIGN.md.
    """
    return {
        "status": "not_implemented",
        "message": "Analysis pipeline not built yet; this is a skeleton response.",
        "received": {
            "company": req.company,
            "title": req.title,
            "jd_chars": len(req.jd_text),
            "has_resume": req.resume_text is not None,
            "job_url": req.job_url,
        },
    }
