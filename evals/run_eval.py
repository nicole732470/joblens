#!/usr/bin/env python3
"""Evaluate the platform against the golden set.

Reads golden_set/samples.csv, calls the backend /analyze for each row, and
scores the system against the manual labels. Only sponsorship (company match)
is implemented today; likelihood / resume-fit / risk / recommendation scoring
is added as those analyses land. Stdlib only.

Usage:
    python3 run_eval.py
    BASE_URL=http://localhost:8000 python3 run_eval.py
"""

from __future__ import annotations

import csv
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SAMPLES = BASE_DIR / "golden_set" / "samples.csv"
RESUME = BASE_DIR / "golden_set" / "resume.md"
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")


def load_resume() -> str | None:
    if not RESUME.exists():
        return None
    text = RESUME.read_text(encoding="utf-8")
    # Ignore the untouched placeholder.
    if "(your resume here)" in text:
        return None
    return text


def analyze(row: dict, resume_text: str | None) -> dict:
    payload = {
        "jd_text": row.get("jd_text") or "",
        "company": row.get("company") or None,
        "title": row.get("title") or None,
        "job_url": row.get("job_url") or None,
    }
    if resume_text:
        payload["resume_text"] = resume_text
    req = urllib.request.Request(
        f"{BASE_URL}/analyze",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def main() -> None:
    if not SAMPLES.exists():
        raise SystemExit(f"No samples file at {SAMPLES}")

    resume_text = load_resume()
    rows = list(csv.DictReader(SAMPLES.open(encoding="utf-8")))
    if not rows:
        raise SystemExit("samples.csv has no rows to evaluate")

    company_match_total = 0
    company_match_correct = 0
    errors = 0

    print(f"Evaluating {len(rows)} sample(s) against {BASE_URL}\n")
    for row in rows:
        rid = row.get("id") or "?"
        try:
            report = analyze(row, resume_text)
        except (urllib.error.URLError, TimeoutError) as e:
            errors += 1
            print(f"[{rid}] ERROR calling backend: {e}")
            continue

        sp = report.get("sponsorship", {})
        matched = bool(sp.get("matched"))
        conf = sp.get("match_confidence")
        matched_name = (sp.get("company") or {}).get("name") if matched else None

        expected_raw = (row.get("expected_company_match") or "").strip().lower()
        verdict = ""
        if expected_raw in ("yes", "no"):
            expected = expected_raw == "yes"
            company_match_total += 1
            ok = matched == expected
            company_match_correct += int(ok)
            verdict = "  OK" if ok else "  MISMATCH"

        detail = f"matched={matched}"
        if matched:
            detail += f" ({matched_name}, {conf})"
        print(f"[{rid}] {detail}{verdict}")

    print("\n--- Summary ---")
    print(f"samples:            {len(rows)}")
    if errors:
        print(f"backend errors:     {errors}")
    if company_match_total:
        acc = company_match_correct / company_match_total
        print(
            f"company match acc:  {company_match_correct}/{company_match_total} "
            f"({acc:.0%})"
        )
    else:
        print("company match acc:  (no rows labeled with expected_company_match)")
    print("likelihood:         pending (calculate_sponsorship_likelihood not built)")
    print("resume fit / risk / recommendation: pending (analyses not built)")


if __name__ == "__main__":
    main()
