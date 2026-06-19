#!/usr/bin/env python3
"""Evaluate the platform against the golden set.

Reads golden_set/samples.csv, calls the backend /analyze for each row, and
scores the system against the manual labels. Only the sponsorship check
(is the employer in U.S. H-1B data) is implemented today; resume-fit / risk /
recommendation scoring is added as those analyses land. Stdlib only.

Usage:
    python3 run_eval.py
    BASE_URL=http://localhost:8000 python3 run_eval.py
"""

from __future__ import annotations

import csv
import io
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


def read_rows() -> list[dict]:
    """Read samples.csv, tolerating non-UTF-8 exports from Excel/Numbers."""
    raw = SAMPLES.read_bytes()
    text = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("utf-8", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


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
    rows = read_rows()
    if not rows:
        raise SystemExit("samples.csv has no rows to evaluate")

    sponsors_total = 0
    sponsors_correct = 0
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

        expected_raw = (row.get("expected_sponsors") or "").strip().lower()
        verdict = ""
        if expected_raw in ("yes", "no"):
            expected = expected_raw == "yes"
            sponsors_total += 1
            ok = matched == expected
            sponsors_correct += int(ok)
            verdict = "  OK" if ok else "  MISMATCH"

        detail = f"matched={matched}"
        if matched:
            detail += f" ({matched_name}, {conf})"
        print(f"[{rid}] {detail}{verdict}")

    print("\n--- Summary ---")
    print(f"samples:            {len(rows)}")
    if errors:
        print(f"backend errors:     {errors}")
    if sponsors_total:
        acc = sponsors_correct / sponsors_total
        print(f"sponsors (in H-1B data) acc:  {sponsors_correct}/{sponsors_total} ({acc:.0%})")
    else:
        print("sponsors acc:  (no rows labeled with expected_sponsors)")
    print("resume fit / risk / recommendation: pending (analyses not built)")


if __name__ == "__main__":
    main()
