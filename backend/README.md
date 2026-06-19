# Backend — Hop Job Intelligence API

FastAPI service for `/analyze`: JD parsing, resume fit, role/location/company scoring, and Apply/Consider/Skip recommendation.

H-1B **entity resolution** still runs in the Chrome extension (`extension/lib/matcher.js`). The backend uses Postgres for employer index (optional) and pgvector for resume chunks.

## Run

```bash
# from repo root
cp .env.example .env
docker compose up -d --build
curl http://localhost:8000/health
```

## Key routes

| Route | Purpose |
|-------|---------|
| `GET /health` | DB + profile status |
| `POST /analyze` | Full report (sponsorship from extension; fit + recommendation here) |
| `GET /candidate-profile` | Loaded YAML profile (debug) |
| `POST /resume/index` | Chunk + embed resume into pgvector |

## Layout

```
backend/app/
├── main.py              # FastAPI routes
├── tools/
│   ├── jd_parser.py     # LLM JD → structured requirements
│   ├── resume_fit.py    # Vector resume ↔ JD requirements
│   ├── track_match.py   # Title ↔ profile tracks
│   ├── role_priority.py # JD + resume P-tier adjustments
│   ├── company_signals.py
│   ├── recommendation.py
│   └── profile_signals.py
└── schemas/             # Report, CandidateProfile
```

Profile YAML path: `CANDIDATE_PROFILE_PATH` env or `evals/golden_set/candidate_profile.yaml`.

See [`docs/REPORT_SCHEMA.md`](../docs/REPORT_SCHEMA.md) and [`docs/DESIGN.md`](../docs/DESIGN.md).
