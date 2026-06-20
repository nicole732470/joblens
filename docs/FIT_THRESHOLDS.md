# Fit & matching thresholds

How numbers map to UI labels. **Tunable** — adjust constants, re-run
`evals/run_eval.py` against labeled `samples.csv`.

## Architecture (two layers)

| Layer | What | Drives final Apply/Skip? |
|-------|------|--------------------------|
| **Display metrics** | Role P-tier, location tier, company tier, `fit_ratio`, strong/partial/missing | **No** (shown + golden-set eval) |
| **Final verdict** | LLM reads JD + resume + `candidate_profile.yaml` | **Yes** (default `RECOMMENDATION_METHOD=llm`) |
| **Rules fallback** | `fit_ratio` + track priority thresholds in `recommendation.py` | Only when LLM unavailable or `RECOMMENDATION_METHOD=rules` |

Resume fit is still **fully computed** (RAG + per-requirement classification) and
displayed in the extension/web UI. Optimize it via `expected_fit_band` in the
golden set — separately from `expected_decision`.

---

## 1. Job title ↔ profile tracks

**File:** `backend/app/tools/track_match.py`

- Job title embedded vs each track (`label` + `example_titles`).
- Cosine similarity 0–1.
- Want-track match if similarity ≥ **0.30**.
- Avoid-track if similarity ≥ **0.38** and beats want tracks.
- JD body + `role_priority.py` can adjust P-tier after title match.

**Golden set:** `expected_priority`, `expected_track_id`

---

## 2. Resume ↔ each JD requirement (display fit)

**Files:** `resume_store.py`, `resume_fit.py`, `resume_fit_llm.py`

**Step A — RAG:** embed each requirement; retrieve top-**3** resume chunks.

**Step B — Classification:**

| `match_method` | How strong / partial / missing is decided |
|----------------|-------------------------------------------|
| **`llm`** | LLM reads retrieved snippets per requirement |
| **`vector`** | Cosine distance on closest chunk (fallback) |

Vector fallback:

| Distance | Label |
|----------|-------|
| ≤ **0.34** | **strong** |
| **0.34 – 0.52** | **partial** |
| **> 0.52** | **weak** (in `missing`) |

`RESUME_FIT_METHOD=auto|llm|vector`

**Weighted fit ratio** (UI + golden `expected_fit_band`):

```
effective = strong + partial × 0.5 + weak × 0.3
fit_ratio = effective / total_requirements
```

| Band (`expected_fit_band`) | `fit_ratio` |
|----------------------------|-------------|
| **high** | ≥ **0.50** |
| **medium** | **0.28 – 0.49** |
| **low** | **< 0.28** |

Weights: `_PARTIAL_WEIGHT = 0.5`, `_WEAK_WEIGHT = 0.3` in `recommendation.py`
(shared with rules fallback).

---

## 3. Location tier

**File:** `backend/app/tools/profile_signals.py` — `score_location()`

| Tier | `location_score` | Rule (simplified) |
|------|------------------|-------------------|
| P1 | 1.0 | `tier_1` place or strong remote fit |
| P2 | 0.75 | `tier_2` or remote-ok + JD remote |
| P3 | 0.25–0.35 | `tier_3`, onsite unknown, rural |
| — | 0.5 | Unspecified default |

**Golden set:** `expected_location_tier` → `recommendation.location_tier`

---

## 4. Company tier

**File:** `backend/app/tools/company_signals.py` — `score_company()`

Combined score from preferences, industry (NAICS), followers, alumni hints.

| Tier | Rule |
|------|------|
| P1 | score ≥ **0.52** |
| P2 | score ≥ **0.38** |
| P3 | else (dealbreaker industry → forced P3) |

**Not H-1B sponsor odds.** Golden set: `expected_company_tier`

---

## 5. Final verdict (Apply / Near apply / Consider / Skip)

### Default: LLM (`recommendation_llm.py`)

**Env:** `RECOMMENDATION_METHOD=llm` (or `auto` when `LLM_API_KEY` set)

Inputs: full JD, resume text, `candidate_profile.yaml`, optional preflight
hints (track match counts, resume_fit counts).

Output: `decision`, `reasoning`, `summary`, `track_*`, `recommendation_method: llm`

Profile YAML guides intent (P1–P2 tracks, avoid, dealbreakers, trajectory).
The model synthesizes JD + resume; it does **not** read `fit_ratio` as the
decision function.

**Golden set:** `expected_decision`

### Fallback: rules (`recommendation.py` → `_generate_recommendation_rules`)

Used when LLM unavailable or `RECOMMENDATION_METHOD=rules`.

| Verdict | Conditions |
|---------|------------|
| **Apply** | `strong ≥ 2` AND `fit_ratio ≥ 0.50` |
| **Near apply** | Track P1–P2, title sim ≥ 0.30, fit ≥ 0.22, below Apply bar |
| **Consider** | fit ≥ 0.28, or enough partial/weak, or P1–P2 floor ≥ 0.12 |
| **Skip** | P4–P5 track, dealbreakers, avoid track, JD visa veto, low fit |

Hard skips (dealbreakers, JD no-sponsor, avoid track) apply in both paths.

---

## 6. Golden set columns (summary)

| Column | Values |
|--------|--------|
| `expected_sponsors` | `yes` / `no` / `unknown` |
| `expected_priority` | `1`–`5` / `skip` / `unknown` |
| `expected_track_id` | profile track id / `unknown` |
| `expected_location_tier` | `1`–`3` / `unknown` |
| `expected_company_tier` | `1`–`3` / `unknown` |
| `expected_fit_band` | `high` / `medium` / `low` / `unknown` |
| `expected_decision` | `apply` / `near_apply` / `consider` / `skip` / `unknown` |

See `evals/golden_set/README.md` for labeling guidance.
