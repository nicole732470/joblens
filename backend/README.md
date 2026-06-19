# Backend — JobLens API

FastAPI + LangGraph service for `/analyze`: JD parsing, RAG + LLM resume fit, role/location/company scoring, and Apply / Near apply / Consider / Skip.

H-1B **entity resolution** runs in the Chrome extension (`extension/lib/matcher.js`). The backend uses Postgres + pgvector for resume chunks and optional employer index.

## Run

```bash
# from repo root
cp .env.example .env   # set LLM_API_KEY
docker compose up -d --build
curl http://localhost:8000/health
```

## Key routes

| Route | Purpose |
|-------|---------|
| `GET /health` | DB, profile, LLM, orchestration status |
| `POST /analyze` | Full report (LangGraph + ReAct agent) |
| `GET /candidate-profile` | Loaded YAML profile |
| `POST /resume/index` | Chunk + embed resume into pgvector |
| `GET /tools` | List analyze tools |
| `POST /tools/{name}` | Invoke one tool (debug) |
| `GET /observability/traces` | List analyze traces |
| `GET /observability/traces/{run_id}` | One trace JSON |

## Layout

```
backend/app/
├── main.py                 # FastAPI routes
├── graph/
│   ├── workflow.py         # LangGraph compile + invoke
│   ├── agent.py            # ReAct agent
│   ├── nodes.py            # prepare, parse, fill_gaps, …
│   └── assemble.py           # Report from artifacts
├── tools/
│   ├── analyze_tools.py    # 6 LangChain tools
│   ├── jd_parser.py        # LLM JD → requirements
│   ├── resume_fit.py       # RAG + LLM classify (vector fallback)
│   ├── resume_fit_llm.py   # LLM batch classifier
│   ├── track_match.py      # Title ↔ profile tracks
│   ├── role_priority.py    # P-tier adjustments
│   ├── recommendation.py   # Verdict rules
│   ├── profile_signals.py  # Location, dealbreakers
│   ├── company_signals.py
│   ├── observability.py    # Traces + optional LangSmith
│   └── analysis_context.py # Per-run artifacts cache
└── schemas/                # Report, CandidateProfile
```

Profile path: `CANDIDATE_PROFILE_PATH` or `evals/golden_set/candidate_profile.yaml`.

See [`../README.md`](../README.md) for architecture diagrams and glossary.
