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
| `expected_sponsors` | In U.S. H-1B data? | `yes` / `no` / `not sure` / blank |
| `expected_recommendation` | Your apply call (optional) | `apply` / `apply with modifications` / `low priority` / `skip` / `not sure` / blank |
| `notes` | Anything useful | free text |

`expected_sponsors`: **yes** = employer appears in H-1B data; **no** = not found;
**not sure** = you haven't verified — eval skips scoring that row for sponsors.

`expected_recommendation`: your human Apply/Skip judgment (uses profile + resume +
JD only — **not** the H-1B database). Leave blank until you've tried the job in
the extension; use **not sure** when undecided. Values are case-insensitive.

Resume-fit, risk, and recommendation labels are intentionally left out until
those analyses are built; we'll design those columns (including the
multi-dimensional fit: skills / domain / experience / location) at that point.

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

It prints per-sample results and a summary. Right now it scores **sponsorship
accuracy** — i.e. did the lookup correctly find (or not find) the employer in
H-1B data, against your `expected_sponsors` labels. Resume fit, risk, and
recommendation scoring are added as those features land.
