# Golden Set

The labeled evaluation set. **You fill in `samples.csv`** (one row per job
posting); the harness (`evals/run_eval.py`) scores each **product dimension**
against your labels.

Target: **30–50 real job postings**. Example rows ship in `samples.csv` —
replace or extend them.

## What we optimize

The product shows several independent signals. The golden set tracks **accuracy
of each**, not only the final Apply/Skip pill:

| UI signal | Golden column | Compared to |
|-----------|---------------|-------------|
| H-1B sponsor match | `expected_sponsors` | `sponsorship.matched` |
| Role track + P-tier | `expected_priority`, `expected_track_id` | `recommendation.track_priority`, `track_id` |
| Location tier | `expected_location_tier` | `recommendation.location_tier` |
| Company tier | `expected_company_tier` | `company.company_tier` |
| Resume ↔ JD fit (display) | `expected_fit_band` | `fit_ratio` band from `resume_fit` |
| Final verdict | `expected_decision` | `recommendation.decision` (LLM by default) |

**Important:** Resume fit (`fit_ratio`, strong/partial/missing) is still
**computed and shown** in the UI. It is a **display + eval dimension** — not
the primary decision function when `RECOMMENDATION_METHOD=llm`. The LLM reads
full JD + resume + profile YAML for the final verdict; we tune fit scoring
separately against `expected_fit_band`.

## How to fill it

Open `samples.csv` in Excel / Numbers / Google Sheets. One row = one job posting.

| Column | Fill with | Allowed values |
|--------|-----------|----------------|
| `id` | Short unique id | e.g. `ex1`, `job_001` |
| `company` | Company name | free text |
| `title` | Job title | free text |
| `job_url` | Posting link (optional) | URL or blank |
| `jd_text` | Full job description | paste full text |
| `expected_sponsors` | In U.S. H-1B data? | `yes` / `no` / `unknown` / blank |
| `expected_priority` | Role P-tier after title **+ JD** | `1`–`5` / `skip` / `unknown` / blank |
| `expected_track_id` | Profile track id | e.g. `ai_eng`, `pm_eng` / `unknown` / blank |
| `expected_location_tier` | Location fit | `1` / `2` / `3` / `unknown` / blank |
| `expected_company_tier` | Company quality tier | `1` / `2` / `3` / `unknown` / blank |
| `expected_fit_band` | Resume–JD overlap (display metric) | `high` / `medium` / `low` / `unknown` / blank |
| `expected_decision` | Final verdict | `apply` / `near_apply` / `consider` / `skip` / `unknown` / blank |
| `notes` | Anything useful | free text |

Leave any column **blank** until you've judged it; the harness skips scoring
that dimension for that row.

### `expected_sponsors`

`yes` = employer in DOL H-1B data; `no` = not found; `unknown` = not verified.

### `expected_priority` (Role P-tier)

The **Role P** the UI should show (`1`–`5`) after reading **title + JD
together** — same scale as `candidate_profile.yaml` track priorities.

This is **fit you can actually do**, not “how much you want the job”:

- **Role family** — Customer Success ≠ Product/AI; Research Engineer ≠ builder AI if JD expects PhD research.
- **JD hardness** — hardware/HPC-heavy posting can downgrade tier (e.g. analyst title P3 in abstract → P4 for this JD).

`run_eval.py` compares to `recommendation.track_priority`.

### `expected_track_id`

Optional check on **which profile track** matched (e.g. `ai_eng`, `pm_eng`,
`customer_success`). Use when title is ambiguous.

### `expected_location_tier`

Your judgment of location fit vs profile `locations`:

| Tier | Meaning |
|------|---------|
| `1` | Preferred (`tier_1` or strong remote fit) |
| `2` | Acceptable |
| `3` | Avoid / no-go / poor remote fit |

Compared to `recommendation.location_tier` from `profile_signals.py`.

### `expected_company_tier`

Company quality vs your preferences (not H-1B odds):

| Tier | Typical system rule |
|------|---------------------|
| `1` | `company_score ≥ 0.52` |
| `2` | `≥ 0.38` |
| `3` | below that or dealbreaker industry |

Compared to `company.company_tier` from `company_signals.py`.

### `expected_fit_band`

Resume–requirement overlap **as shown in the UI** (RAG + per-requirement
classification). Bands used by `run_eval.py`:

| Band | `fit_ratio` (weighted) |
|------|-------------------------|
| `high` | ≥ **50%** |
| `medium` | **28% – 49%** |
| `low` | **< 28%** |

Formula: `effective = strong + partial×0.5 + weak×0.3`, divided by total
requirements. See `docs/FIT_THRESHOLDS.md`.

This does **not** have to match `expected_decision` — e.g. right track (Near
apply) with `medium` fit is valid.

### `expected_decision`

Final **Apply / Near apply / Consider / Skip** — your holistic judgment for
this posting + your resume. Compared to `recommendation.decision`.

With `RECOMMENDATION_METHOD=llm` (default), the backend uses an LLM reading
JD + resume + profile YAML. Tune prompts and profile until **decision acc**
improves on labeled rows.

Legacy `RECOMMENDATION_METHOD=rules` uses `fit_ratio` thresholds instead — only
for fallback / regression.

## Resume

`resume.md` — **dev/eval default only.** `/analyze` uses it when no
`resume_text` is sent. Extension/web uploads override per user.

## Running the evaluation

```bash
cd evals
python3 run_eval.py
# BASE_URL=https://3-128-164-130.sslip.io python3 run_eval.py
```

Summary lines:

- **sponsors acc** — H-1B entity match
- **priority acc** — Role P-tier
- **track_id acc** — Matched profile track
- **location tier acc** — Location P1–P3
- **company tier acc** — Company P1–P3
- **resume fit band acc** — high / medium / low
- **decision acc** — LLM (or rules fallback) verdict

See **`docs/FIT_THRESHOLDS.md`** for all numeric constants.
