# Fit & matching thresholds

How numbers map to labels today. **Tunable** — adjust constants and re-run
`evals/run_eval.py`.

## 1. Job title ↔ your profile tracks (semantic, not keyword)

**File:** `backend/app/tools/track_match.py`

- Job title and each track (`label` + example titles as hints) are embedded.
- **Cosine similarity** 0–1 (higher = closer meaning).
- Title matches a **want** track if similarity ≥ **0.30**.
- Title matches an **avoid** track if similarity ≥ **0.38** and beats want tracks.

Example: «Member of Technical Staff» embeds near «AI Engineer» without listing
that exact string in YAML.

## 2. Resume ↔ each JD requirement (vector / pgvector)

**File:** `backend/app/tools/resume_fit.py`

Each JD requirement is embedded and compared to resume chunks (pgvector cosine
**distance** — lower = closer):

| Distance | Label in report |
|----------|-----------------|
| ≤ **0.34** | **strong** |
| **0.34 – 0.52** | **partial** |
| **> 0.52** | **weak** (shown under gaps) |

Constants: `_STRONG_MAX = 0.34`, `_PARTIAL_MAX = 0.52`.

## 3. Apply / Skip decision (never uses H-1B DB)

**File:** `backend/app/tools/recommendation.py`

From resume fit counts, compute **fit_ratio**:

```
effective = strong + partial + (weak × 0.65)
fit_ratio = effective / total_requirements
```

| fit_ratio | Typical decision |
|-----------|------------------|
| ≥ 0.48 and enough strong | **Apply** |
| ≥ 0.35 or several partial/weak | **Apply with modifications** |
| ≥ 0.15, or **priority 1–2 track match** | at least **Apply with modifications** (not Skip) |
| lower | **Skip** (unless priority 1–2 track + AI JD → bump) |

**Priority floor:** if title semantically matches a **priority 1 or 2** track
(similarity ≥ 0.30), we **do not Skip** on low vector fit alone — minimum
«Apply with modifications».

Hard **Skip** only for: JD visa veto, avoid-track match, or truly zero overlap.

## 4. Golden set labels

| Column | Values |
|--------|--------|
| `expected_sponsors` | `yes` / `no` / `unknown` / blank |
| `expected_priority` | `1`–`5` / `skip` / `unknown` / blank |

`expected_priority` = **your** judgment of how much you want this role (same
scale as profile track priority). Eval compares to system's `track_priority`
from semantic title match — not to Apply/Skip wording.

`ex3` = sample id for the Sourcerer / a16z row in `samples.csv`.
