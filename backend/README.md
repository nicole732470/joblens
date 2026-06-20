# Backend — JobLens API

FastAPI + LangGraph service for `/analyze`: JD parsing, RAG + LLM resume fit,
role/location/company scoring (display + eval), and LLM Apply / Skip with rules
fallback.

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
| `GET /health` | DB, profile, LLM, pipeline status |
| `POST /analyze` | Full report (LangGraph pipeline) |
| `POST /analyze/async` | Background analyze + job poll |
| `GET /candidate-profile` | Loaded YAML profile |
| `POST /resume/index` | Chunk + embed resume into pgvector |
| `GET /observability/traces` | List analyze traces |
| `GET /observability/traces/{run_id}` | One trace JSON |

## Layout

```
backend/app/
├── main.py                 # FastAPI routes
├── graph/
│   ├── workflow.py         # LangGraph compile + invoke
│   ├── nodes.py            # prepare, prefetch, analyze pipeline
│   └── assemble.py         # Report from artifacts
├── tools/
│   ├── analyze_tools.py    # Pipeline step functions
│   ├── jd_parser.py        # LLM JD → requirements
│   ├── resume_fit.py       # RAG + LLM classify (vector fallback)
│   ├── recommendation_llm.py
│   ├── recommendation.py   # Verdict router + rules fallback
│   ├── track_match.py      # Title ↔ profile tracks
│   ├── profile_signals.py  # Location, dealbreakers
│   ├── company_signals.py
│   └── observability.py    # Traces + optional LangSmith
└── schemas/                # Report, CandidateProfile
```

Profile path: `CANDIDATE_PROFILE_PATH` or `evals/golden_set/candidate_profile.yaml`.

See [`../README.md`](../README.md) for architecture diagrams and glossary.
