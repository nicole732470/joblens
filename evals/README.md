# Evaluation

The scoreboard for the platform. Built **before** the agents so every change is
measurable.

## Status

Skeleton only.

## Plan

1. **Golden set** — 30–50 real job postings, each hand-labeled with expected
   outcomes:
   - sponsorship likely? (yes / no / unclear)
   - recommendation (Apply / Apply with modifications / Low Priority / Skip)
   - key missing qualifications
2. **Harness** — offline script that runs the pipeline over the golden set and
   reports retrieval relevance, citation coverage, and recommendation accuracy.
3. **Tracking** — LangSmith for traces + regression across prompt/model versions.

## Planned layout

```
evals/
├── golden_set/        # labeled postings (jsonl) + resumes used for fit tests
├── run_eval.py        # offline harness
└── metrics/           # saved results per run for regression comparison
```
