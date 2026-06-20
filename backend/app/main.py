import logging
import threading
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

from app.auth import (
    create_access_token,
    create_user,
    ensure_auth_schema,
    fetch_user_by_email,
    get_current_user_id,
    require_user_id,
    verify_password,
)
from app.analyze_jobs import create_job, fail_job, finish_job, get_job, update_job
from app.config import settings
from app.db import check_db_connection
from app.graph.workflow import run_analyze_workflow
from app.schemas.candidate_profile import CandidateProfile
from app.schemas.report import Report
from app.tools.entity_resolver import get_resolver
from app.tools.job_url import parse_job_url
from app.tools.llm import llm_available
from app.tools.observability import (
    bind_run_id,
    configure_langsmith,
    get_trace_steps,
    list_recent_traces,
    load_trace,
    start_trace,
)
from app.tools.pdf_text import extract_pdf_text
from app.tools.profile_loader import get_candidate_profile, load_candidate_profile, set_request_profile
from app.tools.resume_store import index_resume
from app.user_store import (
    get_primary_resume_text,
    get_user_profile,
    get_user_resume_status,
    is_owner_email,
    save_user_profile,
    save_user_resume,
    sync_owner_from_golden,
)


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
            "recommendation_method": rec.recommendation_method,
            "adjustments": rec.technical_penalty_hits,
            "note": (
                "LLM: reads JD + resume + profile YAML for final verdict. "
                "Rules (fallback): weighted fit_ratio thresholds."
                if rec.recommendation_method == "llm"
                else "Deterministic fit_ratio + track priority thresholds."
            ),
        },
        "debug": "DevTools → Network → POST /analyze → Response JSON → explain",
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        get_resolver()
    except Exception:
        pass
    try:
        ensure_auth_schema()
    except Exception:
        pass
    configure_langsmith()
    yield


app = FastAPI(title="JobLens API", version="3.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuthRegisterRequest(BaseModel):
    email: EmailStr
    password: str


class AuthLoginRequest(BaseModel):
    email: EmailStr
    password: str


class ParseJobUrlRequest(BaseModel):
    url: str


class AnalyzeRequest(BaseModel):
    jd_text: str = ""
    company: str | None = None
    title: str | None = None
    resume_text: str | None = None
    job_url: str | None = None
    job_location: str | None = None
    linkedin_followers: int | None = None
    alumni_hints: list[str] = []


class IndexResumeRequest(BaseModel):
    resume_text: str
    resume_key: str | None = None


def _apply_user_context(user_id: uuid.UUID | None) -> str | None:
    """Load profile + primary resume for authenticated requests."""
    if user_id is None:
        set_request_profile(None)
        return None
    set_request_profile(get_user_profile(user_id))
    return get_primary_resume_text(user_id)


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
        "pipeline": "deterministic",
        "langsmith": bool(settings.langsmith_api_key),
        "trace_dir": settings.trace_dir,
        "api_version": "3.3.0",
    }


@app.post("/auth/register")
def auth_register(req: AuthRegisterRequest) -> dict:
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="password must be at least 8 characters")
    if fetch_user_by_email(req.email):
        raise HTTPException(status_code=409, detail="email already registered")
    user_id = create_user(req.email, req.password)
    try:
        if is_owner_email(req.email) and settings.owner_sync_golden_on_login:
            sync_owner_from_golden(req.email)
        else:
            save_user_profile(user_id, load_candidate_profile())
    except FileNotFoundError:
        pass
    token = create_access_token(user_id, req.email)
    return {"token": token, "user_id": str(user_id), "email": req.email.lower()}


@app.post("/auth/login")
def auth_login(req: AuthLoginRequest) -> dict:
    row = fetch_user_by_email(req.email)
    if not row or not verify_password(req.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="invalid email or password")
    if is_owner_email(row["email"]) and settings.owner_sync_golden_on_login:
        try:
            sync_owner_from_golden(row["email"])
        except FileNotFoundError:
            pass
    token = create_access_token(row["id"], row["email"])
    return {"token": token, "user_id": str(row["id"]), "email": row["email"]}


@app.get("/me/profile", response_model=CandidateProfile)
def me_profile(user_id: uuid.UUID = Depends(require_user_id)) -> CandidateProfile:
    return get_user_profile(user_id)


@app.get("/me/resume")
def me_resume(user_id: uuid.UUID = Depends(require_user_id)) -> dict:
    return get_user_resume_status(user_id)


@app.put("/me/profile", response_model=CandidateProfile)
def me_profile_update(
    profile: CandidateProfile,
    user_id: uuid.UUID = Depends(require_user_id),
) -> CandidateProfile:
    save_user_profile(user_id, profile)
    return profile


@app.post("/jobs/parse-url")
def jobs_parse_url(req: ParseJobUrlRequest) -> dict:
    return parse_job_url(req.url)


@app.post("/resume/upload")
async def resume_upload(
    file: UploadFile = File(...),
    user_id: uuid.UUID = Depends(require_user_id),
) -> dict:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF files only")
    data = await file.read()
    if len(data) > 5_000_000:
        raise HTTPException(status_code=400, detail="file too large (max 5MB)")
    try:
        text = extract_pdf_text(data)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e)) from e
    rid = save_user_resume(user_id, file.filename or "resume.pdf", text)
    indexed = index_resume(text, resume_key=f"user_{user_id}")
    return {
        "resume_id": str(rid),
        "filename": file.filename,
        "chars": len(text),
        "indexed": indexed.get("indexed", False),
    }


@app.get("/candidate-profile", response_model=CandidateProfile)
def candidate_profile(user_id: uuid.UUID | None = Depends(get_current_user_id)) -> CandidateProfile:
    if user_id:
        return get_user_profile(user_id)
    return get_candidate_profile()


@app.get("/observability/traces")
def traces_list(limit: int = 20) -> dict:
    return {"traces": list_recent_traces(limit=limit)}


@app.get("/observability/traces/{run_id}")
def traces_get(run_id: str) -> dict:
    data = load_trace(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return data


@app.post("/resume/index")
def resume_index(req: IndexResumeRequest) -> dict:
    try:
        return index_resume(req.resume_text, req.resume_key, force=True)
    except Exception as e:  # noqa: BLE001
        return {"indexed": False, "reason": str(e)}


def _resolve_analyze_inputs(req: AnalyzeRequest, user_id: uuid.UUID | None) -> dict:
    stored_resume = _apply_user_context(user_id)

    jd_text = req.jd_text or ""
    company = req.company
    title = req.title
    job_url = req.job_url
    job_location = req.job_location

    if job_url and len(jd_text.strip()) < 80:
        parsed = parse_job_url(job_url)
        if parsed.get("ok"):
            jd_text = parsed.get("jd_text") or jd_text
            company = company or parsed.get("company")
            title = title or parsed.get("title")
        elif not jd_text.strip():
            raise HTTPException(status_code=400, detail=parsed.get("reason", "URL parse failed"))

    if len(jd_text.strip()) < 40:
        raise HTTPException(status_code=400, detail="job description too short")

    from app.tools.job_url import looks_like_job_posting

    jd_ok, jd_reason = looks_like_job_posting(jd_text, title or "")
    if not jd_ok:
        raise HTTPException(
            status_code=400,
            detail=jd_reason or "text does not look like a job description",
        )

    resume_text = req.resume_text or stored_resume
    return {
        "jd_text": jd_text,
        "company_name": company,
        "title": title,
        "resume_text": resume_text,
        "job_url": job_url,
        "job_location": job_location,
        "linkedin_followers": req.linkedin_followers,
        "alumni_hints": req.alumni_hints,
    }


def _run_analyze_job(
    job_id: str,
    run_id: str,
    workflow_kwargs: dict,
    user_id: uuid.UUID | None,
) -> None:
    bind_run_id(run_id)
    try:
        _apply_user_context(user_id)
        update_job(job_id, phase="workflow", message="Analyzing job match…")
        report = run_analyze_workflow(**workflow_kwargs, build_explain=_build_explain)
        finish_job(job_id, report=report.model_dump())
    except Exception as e:  # noqa: BLE001
        logging.exception("analyze job %s failed", job_id)
        fail_job(job_id, error=str(e))
    finally:
        set_request_profile(None)


@app.post("/analyze", response_model=Report)
def analyze(
    req: AnalyzeRequest,
    user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> Report:
    workflow_kwargs = _resolve_analyze_inputs(req, user_id)
    start_trace()
    try:
        return run_analyze_workflow(**workflow_kwargs, build_explain=_build_explain)
    finally:
        set_request_profile(None)


@app.post("/analyze/async")
def analyze_async(
    req: AnalyzeRequest,
    user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> dict:
    """Start analyze in background; poll GET /analyze/jobs/{job_id} for steps + result."""
    workflow_kwargs = _resolve_analyze_inputs(req, user_id)
    run_id = start_trace()
    job_id = create_job(run_id=run_id)
    threading.Thread(
        target=_run_analyze_job,
        args=(job_id, run_id, workflow_kwargs, user_id),
        daemon=True,
    ).start()
    return {"job_id": job_id, "run_id": run_id, "status": "running"}


@app.get("/analyze/jobs/{job_id}")
def analyze_job_poll(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    rid = job.get("run_id")
    if rid:
        job["steps"] = get_trace_steps(rid)
    return job
