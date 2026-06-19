# Golden Set

The labeled evaluation set. **You fill in `samples.csv`** (one row per job
posting); the harness (`evals/run_eval.py`) scores the system against your
labels.

Target: **30–50 real job postings**. Two example rows ship in `samples.csv` —
replace or delete them.

## How to fill it

Open `samples.csv` in Excel / Numbers / Google Sheets (it's a normal
spreadsheet). One row = one job posting you want to evaluate.

| Column | Fill with | Allowed values |
|--------|-----------|----------------|
| `id` | A short unique id | e.g. `job_001` |
| `company` | Company name from the posting | free text |
| `title` | Job title | free text |
| `job_url` | Link to the posting (optional) | URL or blank |
| `jd_text` | The full job description text | free text (paste it in) |
| `expected_sponsors` | In U.S. H-1B data? | `yes` / `no` / `unknown` / blank |
| `expected_priority` | Role track tier (P1–P5) | `1`–`5` / `skip` / `unknown` / blank |
| `expected_decision` | Apply verdict | `apply` / `near_apply` / `consider` / `skip` / `unknown` / blank |
| `notes` | Anything useful | free text |

**`expected_sponsors`:** `yes` = in H-1B data; `no` = not found; **`unknown`** = not
verified yet (eval skips).

**`expected_priority`:** the **Role P-tier** the UI should show (`1`–`5` on the
report) after reading **title + JD together**. Same scale as
`candidate_profile.yaml` track priorities (1 = strongest fit tier, higher = weaker).

This is **not** how much you “want” the job. It is **fit you can actually do**:

- **Role family** — e.g. Customer Success is not Product or AI; Research Engineer
  is not the same as a builder AI role if the JD expects a PhD research path.
- **JD hardness** — even when the title family fits, a very hardware / HPC / GPU-heavy
  posting can **downgrade** the tier (e.g. Analyst-shaped title at P3 in the abstract,
  but P4 for this specific JD).

Examples from the sample set:

| Job | P | Why |
|-----|---|-----|
| MTS @ a16z startup | 1 | Core AI/builder track, JD matches |
| Technical CSM @ HERE | 3 | Doable, not Product/AI; moderate tech bar |
| Applied Research Engineer @ Salesforce | 4 | Research track; PhD-style path you don’t have |
| Technical Business Analyst (HPC/Linux) | 4 | Analyst family, but JD too hardware-core |

`run_eval.py` compares this to the system’s `track_priority`. Mismatches usually
mean the backend still weights **title-only track match** and not JD penalties yet —
not that your label is wrong.

**`expected_decision`:** rule-based verdict — `apply` / `near_apply` / `consider` / `skip`.
Compared to the report `decision` field (`Apply`, `Consider`, or `Skip`). Separate
from Role P-tier.

Sample ids: `ex1`, `ex2`, `ex3`, … — short row keys only.

See **`docs/FIT_THRESHOLDS.md`** for resume strong/partial/gap scoring.

Tips:
- Leave `expected_sponsors` blank if you haven't judged it yet; the harness just
  skips scoring that row.
- Avoid stray commas in `notes` unless the cell is quoted (commas split
  columns); a spreadsheet handles the quoting for you.

## Resume

`resume.md` — **dev/eval default only.** The backend reads this file when
`/analyze` gets no `resume_text`. Later, the Chrome extension sends each user's
own upload in the request, which overrides this file. Do not assume every user
shares one repo-bundled resume in production.

## Running the evaluation

Make sure the backend is up (`docker compose up -d`), then:

```bash
cd evals
python3 run_eval.py
```

It prints per-sample results and a summary:

- **sponsors acc** — H-1B employer match vs `expected_sponsors`
- **priority acc** — Role P-tier vs `expected_priority`
- **decision acc** — Apply / Near apply / Consider / Skip vs `expected_decision` (when filled in)
