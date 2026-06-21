# Golden set

One CSV row represents one job posting evaluated against the profile and resume
in this directory. Labels are human judgments; leave uncertain fields blank or
write `unknown`.

## Columns

| Column | Meaning | Allowed labels |
|---|---|---|
| `id` | stable sample ID | unique text |
| `company`, `title`, `job_url`, `jd_text` | API inputs | text |
| `expected_sponsors` | employer found in DOL/LCA history | `yes`, `no`, `unknown` |
| `expected_priority` | Role tier after validation/penalties | `1`, `2`, `3`, `4`, `unknown` |
| `expected_track_id` | configured track family | track ID, blank for unmatched, `unknown` |
| `expected_location_tier` | Location tier | `1`–`4`, `unknown` |
| `expected_company_tier` | personalized Company tier | `1`–`4`, `unknown` |
| `expected_fit_band` | rough aggregate Resume fit | `high`, `medium`, `low`, `unknown` |
| `expected_decision` | holistic verdict | `apply`, `near_apply`, `consider`, `skip`, `unknown` |
| `notes` | rationale or known ambiguity | free text |

Every expected field is optional.

## Labels that look similar

`expected_track_id` and `expected_priority` are related but not duplicates:

- Track checks the role-family classification.
- Priority checks the configured tier after an allowed technical penalty.
- An unmatched role has blank `expected_track_id` and normally P4.

Only label Track when the role clearly belongs to a configured family.

`expected_fit_band` is deliberately approximate. It evaluates the aggregate
Resume display score, not each Strong/Partial/Weak/Gap requirement label:

| Band | Weighted Resume score |
|---|---|
| `high` | ≥ 50% |
| `medium` | 28%–49% |
| `low` | < 28% |

Requirement weights are Strong 1.0, Partial 0.5, Weak 0.25, Gap 0.

## P-tier interpretation

- P1: strongest target
- P2: good target
- P3: acceptable/lower priority
- P4: unmatched or extremely low

Users configure P1–P3 only. An unmatched P4 is not itself a final Skip. An
explicit avoid track is different and may veto.

## Labeling workflow

1. Preserve the complete JD and canonical title/company/location.
2. Label each dimension independently before choosing Final Verdict.
3. Add a short note for ambiguous or regression-critical cases.
4. Run the harness after prompt, threshold, Profile, or parser changes.
5. Inspect the test-account Debug trace for mismatches.

For Web/extension stability, one logical job may later have multiple input
variants. Those variants should share expected dimension bands while preserving
their different raw JD inputs.

## Run

```bash
cd evals
python3 run_eval.py
BASE_URL=https://3-128-164-130.sslip.io python3 run_eval.py
```

Definitions and guardrails: [`../../docs/SCORING_STANDARD.md`](../../docs/SCORING_STANDARD.md).
