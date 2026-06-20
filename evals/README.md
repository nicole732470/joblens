# Evaluation

Offline scoreboard for the platform — every product dimension gets a golden-set
label and a line in `run_eval.py` summary.

## Status

- **Golden set:** `golden_set/samples.csv` — multi-column labels (see README there)
- **Harness:** `run_eval.py` — calls `POST /analyze`, reports per-dimension accuracy
- **Traces:** optional LangSmith + `logs/traces/` JSON

## What we measure

Each row in `samples.csv` can label:

| Dimension | Column | API field |
|-----------|--------|-----------|
| H-1B entity match | `expected_sponsors` | `sponsorship.matched` |
| Role P-tier | `expected_priority` | `recommendation.track_priority` |
| Profile track | `expected_track_id` | `recommendation.track_id` |
| Location tier | `expected_location_tier` | `recommendation.location_tier` |
| Company tier | `expected_company_tier` | `company.company_tier` |
| Resume fit (display) | `expected_fit_band` | `fit_ratio` from `resume_fit` |
| Final verdict | `expected_decision` | `recommendation.decision` |

Resume fit is still computed and shown in the UI; golden `expected_fit_band`
optimizes that layer **separately** from `expected_decision` (LLM verdict).

## Run

```bash
cd evals
python3 run_eval.py
BASE_URL=http://localhost:8000 python3 run_eval.py
```

Target: **30–50** labeled postings. Leave columns blank until judged.

## Layout

```
evals/
├── golden_set/
│   ├── samples.csv
│   ├── resume.md
│   ├── candidate_profile.yaml
│   └── README.md
└── run_eval.py
```

Threshold reference: `docs/FIT_THRESHOLDS.md`
