# Evaluation

`run_eval.py` sends every labeled posting to the same `/analyze` API used by
Web and extension, then scores each independent dimension.

```bash
cd evals
python3 run_eval.py
BASE_URL=https://3-128-164-130.sslip.io python3 run_eval.py
```

Assets:

```text
golden_set/candidate_profile.yaml   guest/eval intent
golden_set/resume.md                eval resume
golden_set/samples.csv              job inputs and optional labels
golden_set/README.md                labeling guide
run_eval.py                         stdlib-only harness
```

Blank and `unknown` labels are excluded from accuracy. The harness reports
H-1B, Role tier/track, Location, Company, Resume band, and Final Verdict
separately; a strong final score must not hide a broken dimension.

The source of truth for definitions and thresholds is
[`docs/SCORING_STANDARD.md`](../docs/SCORING_STANDARD.md).
