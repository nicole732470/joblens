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
| `expected_company_match` | Should our H-1B lookup find this employer? | `yes` / `no` / blank |
| `expected_sponsorship_likelihood` | Your judgment of sponsorship odds | `High` / `Medium` / `Low` / `Unknown` |
| `expected_recommendation` | What the right call is | `Apply` / `Apply with modifications` / `Low priority` / `Skip` |
| `expected_strong_matches` | Skills/areas your resume clearly covers | `;`-separated, e.g. `Python;RAG` |
| `expected_missing_quals` | Key things you're missing | `;`-separated |
| `notes` | Anything useful | free text |

Tips:
- Use `;` to separate multiple items inside one cell (don't use commas — commas
  split columns).
- Leave a cell blank if you haven't judged it yet; the harness just skips
  scoring that dimension for that row.
- `resume.md` holds the single resume used for resume-fit scoring — paste yours
  there.

## Resume

`resume.md` — paste your resume text once. It's reused for every sample's
resume-fit evaluation (added in a later phase).

## Running the evaluation

Make sure the backend is up (`docker compose up -d`), then:

```bash
cd evals
python3 run_eval.py
```

It prints per-sample results and a summary. Right now it scores **company match
accuracy** (sponsorship is the only implemented analysis). Likelihood, resume
fit, risk, and recommendation scoring are added as those features land.
