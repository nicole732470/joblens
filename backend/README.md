# JobLens backend

FastAPI + LangGraph service for authentication, job analysis, H-1B lookup,
resume RAG, company research, and structured decision traces.

## Run

From the repository root:

```bash
cp .env.example .env
docker compose up -d --build
curl http://localhost:8000/health
```

## Code map

```text
app/
  main.py                  routes, auth context, sync/async analyze entry
  analyze_jobs.py          in-memory async job state
  auth.py, user_store.py   JWT accounts, profiles, resumes
  graph/
    workflow.py            LangGraph topology
    nodes.py               prepare, prefetch, analyze nodes
    assemble.py            artifacts → Report
  schemas/
    candidate_profile.py   user intent contract
    report.py              API response contract
  tools/
    jd_parser.py           structured JD extraction
    resume_fit*.py         pgvector retrieval + four-band classification
    independent_decisions.py
                             parallel Role/Location/Profile decisions
    company_research.py    Tavily source discovery + cache
    company_signals.py     personalized Company scoring
    recommendation*.py     final rules and boundary LLM
    sponsorship.py         DOL/LCA employer history
    observability.py       run traces
```

## Analyze flow

`POST /analyze/async` returns a `job_id`; poll
`GET /analyze/jobs/{job_id}` until the report is ready.

1. Load DB profile/resume or guest golden defaults.
2. Parallel H-1B lookup and JD parse.
3. Resume fit and Company evidence scoring.
4. Parallel Role, Location, and Preference/Dealbreaker decisions.
5. Clear guardrails or boundary Final Verdict LLM.
6. Assemble `Report` and optional trace JSON.

## Important routes

| Route | Purpose |
|---|---|
| `GET /health` | database, LLM, company research status |
| `POST /analyze`, `/analyze/async` | full report |
| `POST /sponsorship/lookup` | fast H-1B lookup |
| `/auth/*`, `/me/*` | account, profile, resume |
| `POST /jobs/parse-url` | web URL ingestion |
| `/observability/traces*` | debug-account-only traces |

## Verify and deploy

```bash
PYTHONPATH=backend pytest -q backend/tests
```

Production:

```bash
cd /opt/joblens && git pull && bash deploy/ec2-redeploy.sh
```

See [architecture](../docs/ARCHITECTURE.md),
[scoring](../docs/SCORING_STANDARD.md), and
[database](../docs/DATABASE.md).
