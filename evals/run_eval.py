#!/usr/bin/env python3
"""Evaluate the platform against the golden set.

Reads golden_set/samples.csv, calls /analyze, scores sponsorship + priority labels.
Stdlib only.

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
    if "(your resume here)" in text:
        return None
    return text


def read_rows() -> list[dict]:
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


def norm_sponsors(raw: str) -> str:
    v = (raw or "").strip().lower().replace("_", " ")
    if v in ("yes", "y"):
        return "yes"
    if v in ("no", "n"):
        return "no"
    if v in ("unknown", "unk", "not sure", "not_sure", "unsure", "?"):
        return "unknown"
    return ""


def norm_priority(raw: str) -> str:
    """Golden-set track tier label: 1-5, skip, unknown, or blank."""
    v = (raw or "").strip().lower().replace("_", " ")
    if v in ("skip", "pass"):
        return "skip"
    if v in ("unknown", "unk", "not sure", "not_sure", "unsure", "?"):
        return "unknown"
    if v.isdigit() and 1 <= int(v) <= 5:
        return v
    return ""


def norm_decision(raw: str) -> str:
    """Golden-set verdict label: apply, near apply, consider, skip, unknown, or blank."""
    v = (raw or "").strip().lower().replace("_", " ")
    if v in ("apply", "yes", "y"):
        return "apply"
    if v in ("near apply", "nearapply"):
        return "near apply"
    if v in (
        "consider",
        "maybe",
        "modifications",
        "apply with modifications",
        "low priority",
        "later",
    ):
        return "consider"
    if v in ("skip", "no", "pass"):
        return "skip"
    if v in ("unknown", "unk", "not sure", "not_sure", "unsure", "?"):
        return "unknown"
    return ""


def api_decision_bucket(decision: str | None) -> str:
    d = (decision or "").strip().lower()
    if d == "apply":
        return "apply"
    if d in ("near apply", "near_apply"):
        return "near apply"
    if d in ("consider", "apply with modifications", "low priority"):
        return "consider"
    if d == "skip":
        return "skip"
    return ""


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
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.load(resp)


def main() -> None:
    if not SAMPLES.exists():
        raise SystemExit(f"No samples file at {SAMPLES}")

    resume_text = load_resume()
    rows = read_rows()
    if not rows:
        raise SystemExit("samples.csv has no rows to evaluate")

    sponsors_total = sponsors_correct = sponsors_unknown = 0
    priority_total = priority_correct = priority_unknown = 0
    decision_total = decision_correct = decision_unknown = 0
    errors = 0

    print(f"Evaluating {len(rows)} sample(s) against {BASE_URL}\n")

    for row in rows:
        rid = row.get("id") or "?"
        try:
            report = analyze(row, resume_text)
        except (urllib.error.URLError, TimeoutError) as e:
            errors += 1
            print(f"[{rid}] ERROR: {e}")
            continue

        sp = report.get("sponsorship", {})
        matched = bool(sp.get("matched"))
        detail = f"sponsors matched={matched}"

        expected_sp = norm_sponsors(row.get("expected_sponsors") or "")
        verdict: list[str] = []
        if expected_sp == "unknown":
            sponsors_unknown += 1
            verdict.append("sponsors=unknown (skipped)")
        elif expected_sp in ("yes", "no"):
            sponsors_total += 1
            ok = matched == (expected_sp == "yes")
            sponsors_correct += int(ok)
            verdict.append("sponsors OK" if ok else "sponsors MISMATCH")

        rec = report.get("recommendation") or {}
        if rec.get("track_priority") is not None:
            detail += f" | track P{rec['track_priority']} ({rec.get('track_label', '?')})"
        if rec.get("fit_ratio") is not None:
            detail += f" | fit {rec['fit_ratio']:.0%}"
        if rec.get("decision"):
            detail += f" | → {rec['decision']}"

        # expected_priority column (legacy alias: expected_recommendation)
        raw_pri = row.get("expected_priority") or row.get("expected_recommendation") or ""
        expected_pri = norm_priority(raw_pri)
        if expected_pri == "unknown":
            priority_unknown += 1
            verdict.append("priority=unknown (skipped)")
        elif expected_pri == "skip":
            priority_total += 1
            ok = api_decision_bucket(rec.get("decision")) == "skip"
            priority_correct += int(ok)
            verdict.append("priority OK" if ok else "priority MISMATCH (want skip)")
        elif expected_pri in ("1", "2", "3", "4", "5"):
            priority_total += 1
            actual = rec.get("track_priority")
            ok = actual is not None and int(actual) == int(expected_pri)
            priority_correct += int(ok)
            verdict.append(
                f"priority OK" if ok else f"priority MISMATCH (want P{expected_pri}, got P{actual})"
            )

        raw_dec = row.get("expected_decision") or ""
        expected_dec = norm_decision(raw_dec)
        if expected_dec == "unknown":
            decision_unknown += 1
            verdict.append("decision=unknown (skipped)")
        elif expected_dec in ("apply", "near apply", "consider", "skip"):
            decision_total += 1
            actual_dec = api_decision_bucket(rec.get("decision"))
            ok = actual_dec == expected_dec
            decision_correct += int(ok)
            verdict.append(
                "decision OK"
                if ok
                else f"decision MISMATCH (want {expected_dec}, got {actual_dec or '?'})"
            )

        pending = report.get("pending") or []
        if pending:
            detail += f" | pending:{','.join(pending)}"

        v = f"  {' · '.join(verdict)}" if verdict else ""
        print(f"[{rid}] {detail}{v}")

    print("\n--- Summary ---")
    print(f"samples: {len(rows)}")
    if errors:
        print(f"errors:  {errors}")
    if sponsors_total:
        print(f"sponsors acc: {sponsors_correct}/{sponsors_total} ({sponsors_correct/sponsors_total:.0%})")
    if sponsors_unknown:
        print(f"sponsors unknown (skipped): {sponsors_unknown}")
    if priority_total:
        print(f"priority acc: {priority_correct}/{priority_total} ({priority_correct/priority_total:.0%})")
    if priority_unknown:
        print(f"priority unknown (skipped): {priority_unknown}")
    if decision_total:
        print(
            f"decision acc: {decision_correct}/{decision_total} "
            f"({decision_correct/decision_total:.0%})"
        )
    if decision_unknown:
        print(f"decision unknown (skipped): {decision_unknown}")
    print("\nThresholds: docs/FIT_THRESHOLDS.md")


if __name__ == "__main__":
    main()
