import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.db import check_db_connection
from app.graph.workflow import list_analyze_tools, run_analyze_workflow, run_tool_by_name
from app.schemas.candidate_profile import CandidateProfile
from app.schemas.report import Report
from app.tools.entity_resolver import get_resolver
from app.tools.llm import llm_available
from app.tools.observability import start_trace
from app.tools.profile_loader import get_candidate_profile
from app.tools.resume_store import index_resume


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


def _build_explain(recommendation, company) -> dict:
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
    try:
        get_resolver()
    except Exception:
        pass
    yield


app = FastAPI(title="Job Intelligence API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


class ToolInvokeRequest(BaseModel):
    arguments: dict = {}


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
        "llm": "configured" if llm_available() else "missing_key",
        "resume_fit_method": settings.resume_fit_method,
        "orchestration": "langgraph",
    }


@app.get("/candidate-profile", response_model=CandidateProfile)
def candidate_profile() -> CandidateProfile:
    return get_candidate_profile()


@app.get("/tools")
def tools_list() -> dict:
    """Registered analyze tools (same functions LangGraph nodes and tool-calling use)."""
    return {"tools": list_analyze_tools()}


@app.post("/tools/{tool_name}")
def tools_invoke(tool_name: str, req: ToolInvokeRequest) -> dict:
    """Direct tool invocation for debugging / agent tool-calling integrations."""
    try:
        result = run_tool_by_name(tool_name, **req.arguments)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown tool: {tool_name}") from None
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"tool": tool_name, "result": result}


@app.post("/resume/index")
def resume_index(req: IndexResumeRequest) -> dict:
    try:
        return index_resume(req.resume_text, req.resume_key)
    except Exception as e:  # noqa: BLE001
        return {"indexed": False, "reason": str(e)}


@app.post("/analyze", response_model=Report)
def analyze(req: AnalyzeRequest) -> Report:
    start_trace()
    return run_analyze_workflow(
        jd_text=req.jd_text,
        company_name=req.company,
        title=req.title,
        resume_text=req.resume_text,
        job_url=req.job_url,
        linkedin_followers=req.linkedin_followers,
        alumni_hints=req.alumni_hints,
        build_explain=_build_explain,
    )
