#!/usr/bin/env python3
"""Evaluate the platform against the golden set.

Reads golden_set/samples.csv, calls /analyze, scores labeled dimensions:
sponsorship, role track/priority, location tier, company tier, resume fit band,
and final LLM verdict.

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

# Resume fit band thresholds (display metric — same weights as recommendation rules).
_FIT_PARTIAL_WEIGHT = 0.5
_FIT_WEAK_WEIGHT = 0.25
_FIT_BAND_HIGH = 0.50
_FIT_BAND_MEDIUM = 0.28


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
    v = (raw or "").strip().lower().replace("_", " ")
    if v in ("skip", "pass"):
        return "skip"
    if v in ("unknown", "unk", "not sure", "not_sure", "unsure", "?"):
        return "unknown"
    if v.isdigit() and 1 <= int(v) <= 5:
        return v
    return ""


def norm_tier(raw: str) -> str:
    """Location or company tier: 1-4, unknown, or blank."""
    v = (raw or "").strip().lower().replace("_", " ")
    if v in ("unknown", "unk", "not sure", "not_sure", "unsure", "?"):
        return "unknown"
    if v.isdigit() and 1 <= int(v) <= 4:
        return v
    return ""


def norm_track_id(raw: str) -> str:
    return (raw or "").strip().lower().replace(" ", "_")


def norm_fit_band(raw: str) -> str:
    v = (raw or "").strip().lower().replace("_", " ")
    if v in ("high", "h", "strong"):
        return "high"
    if v in ("medium", "med", "mid", "moderate", "partial"):
        return "medium"
    if v in ("low", "l", "weak", "poor"):
        return "low"
    if v in ("unknown", "unk", "not sure", "not_sure", "unsure", "?"):
        return "unknown"
    return ""


def norm_decision(raw: str) -> str:
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


def compute_fit_ratio(report: dict) -> float | None:
    rec = report.get("recommendation") or {}
    if rec.get("fit_ratio") is not None:
        return float(rec["fit_ratio"])

    rf = report.get("resume_fit") or {}
    if not rf.get("available"):
        return None
    strong = len(rf.get("strong_matches") or [])
    partial = len(rf.get("partial_matches") or [])
    missing = rf.get("missing") or []
    weak = sum(1 for c in missing if c.get("resume_evidence_ids"))
    total = strong + partial + len(missing)
    if total == 0:
        return None
    effective = strong + partial * _FIT_PARTIAL_WEIGHT + weak * _FIT_WEAK_WEIGHT
    return effective / total


def api_fit_band(report: dict) -> str | None:
    ratio = compute_fit_ratio(report)
    if ratio is None:
        return None
    if ratio >= _FIT_BAND_HIGH:
        return "high"
    if ratio >= _FIT_BAND_MEDIUM:
        return "medium"
    return "low"


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


def _score_labeled(
    expected: str,
    ok: bool,
    *,
    total_key: str,
    correct_key: str,
    unknown_key: str,
    label: str,
    counters: dict,
) -> str:
    if expected == "unknown":
        counters[unknown_key] += 1
        return f"{label}=unknown (skipped)"
    if not expected:
        return ""
    counters[total_key] += 1
    counters[correct_key] += int(ok)
    return f"{label} OK" if ok else f"{label} MISMATCH"


def main() -> None:
    if not SAMPLES.exists():
        raise SystemExit(f"No samples file at {SAMPLES}")

    resume_text = load_resume()
    rows = read_rows()
    if not rows:
        raise SystemExit("samples.csv has no rows to evaluate")

    counters = {
        "sponsors_total": 0,
        "sponsors_correct": 0,
        "sponsors_unknown": 0,
        "priority_total": 0,
        "priority_correct": 0,
        "priority_unknown": 0,
        "track_total": 0,
        "track_correct": 0,
        "track_unknown": 0,
        "location_total": 0,
        "location_correct": 0,
        "location_unknown": 0,
        "company_total": 0,
        "company_correct": 0,
        "company_unknown": 0,
        "fit_total": 0,
        "fit_correct": 0,
        "fit_unknown": 0,
        "decision_total": 0,
        "decision_correct": 0,
        "decision_unknown": 0,
    }
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
        rec = report.get("recommendation") or {}
        co = report.get("company") or {}
        matched = bool(sp.get("matched"))

        detail_parts = [f"sponsors matched={matched}"]
        if rec.get("track_priority") is not None:
            detail_parts.append(f"track P{rec['track_priority']} ({rec.get('track_label', '?')})")
        if rec.get("track_id"):
            detail_parts.append(f"id={rec['track_id']}")
        if rec.get("location_tier") is not None:
            detail_parts.append(f"loc P{rec['location_tier']}")
        if co.get("company_tier") is not None:
            detail_parts.append(f"co P{co['company_tier']}")
        ratio = compute_fit_ratio(report)
        if ratio is not None:
            detail_parts.append(f"fit {ratio:.0%}")
        band = api_fit_band(report)
        if band:
            detail_parts.append(f"fit_band={band}")
        if rec.get("decision"):
            detail_parts.append(f"→ {rec['decision']}")
        if rec.get("recommendation_method"):
            detail_parts.append(f"via {rec['recommendation_method']}")

        verdict: list[str] = []

        expected_sp = norm_sponsors(row.get("expected_sponsors") or "")
        if expected_sp == "unknown":
            counters["sponsors_unknown"] += 1
            verdict.append("sponsors=unknown (skipped)")
        elif expected_sp in ("yes", "no"):
            counters["sponsors_total"] += 1
            ok = matched == (expected_sp == "yes")
            counters["sponsors_correct"] += int(ok)
            verdict.append("sponsors OK" if ok else "sponsors MISMATCH")

        raw_pri = row.get("expected_priority") or row.get("expected_recommendation") or ""
        expected_pri = norm_priority(raw_pri)
        if expected_pri == "unknown":
            counters["priority_unknown"] += 1
            verdict.append("priority=unknown (skipped)")
        elif expected_pri == "skip":
            counters["priority_total"] += 1
            ok = api_decision_bucket(rec.get("decision")) == "skip"
            counters["priority_correct"] += int(ok)
            verdict.append("priority OK" if ok else "priority MISMATCH (want skip)")
        elif expected_pri in ("1", "2", "3", "4", "5"):
            counters["priority_total"] += 1
            actual = rec.get("track_priority")
            ok = actual is not None and int(actual) == int(expected_pri)
            counters["priority_correct"] += int(ok)
            verdict.append(
                "priority OK" if ok else f"priority MISMATCH (want P{expected_pri}, got P{actual})"
            )

        expected_track = norm_track_id(row.get("expected_track_id") or "")
        if expected_track == "unknown":
            counters["track_unknown"] += 1
            verdict.append("track=unknown (skipped)")
        elif expected_track:
            counters["track_total"] += 1
            actual_track = norm_track_id(rec.get("track_id") or "")
            ok = actual_track == expected_track
            counters["track_correct"] += int(ok)
            verdict.append(
                "track OK" if ok else f"track MISMATCH (want {expected_track}, got {actual_track or '?'})"
            )

        expected_loc = norm_tier(row.get("expected_location_tier") or "")
        v = _score_labeled(
            expected_loc,
            rec.get("location_tier") is not None and int(rec["location_tier"]) == int(expected_loc),
            total_key="location_total",
            correct_key="location_correct",
            unknown_key="location_unknown",
            label="location",
            counters=counters,
        )
        if v:
            if "MISMATCH" in v:
                v = f"location MISMATCH (want P{expected_loc}, got P{rec.get('location_tier', '?')})"
            verdict.append(v)

        expected_co = norm_tier(row.get("expected_company_tier") or "")
        v = _score_labeled(
            expected_co,
            co.get("company_tier") is not None and int(co["company_tier"]) == int(expected_co),
            total_key="company_total",
            correct_key="company_correct",
            unknown_key="company_unknown",
            label="company",
            counters=counters,
        )
        if v:
            if "MISMATCH" in v:
                v = f"company MISMATCH (want P{expected_co}, got P{co.get('company_tier', '?')})"
            verdict.append(v)

        expected_fit = norm_fit_band(row.get("expected_fit_band") or "")
        if expected_fit == "unknown":
            counters["fit_unknown"] += 1
            verdict.append("fit=unknown (skipped)")
        elif expected_fit:
            counters["fit_total"] += 1
            actual_fit = api_fit_band(report) or ""
            ok = actual_fit == expected_fit
            counters["fit_correct"] += int(ok)
            verdict.append(
                "fit OK" if ok else f"fit MISMATCH (want {expected_fit}, got {actual_fit or '?'})"
            )

        expected_dec = norm_decision(row.get("expected_decision") or "")
        if expected_dec == "unknown":
            counters["decision_unknown"] += 1
            verdict.append("decision=unknown (skipped)")
        elif expected_dec in ("apply", "near apply", "consider", "skip"):
            counters["decision_total"] += 1
            actual_dec = api_decision_bucket(rec.get("decision"))
            ok = actual_dec == expected_dec
            counters["decision_correct"] += int(ok)
            verdict.append(
                "decision OK"
                if ok
                else f"decision MISMATCH (want {expected_dec}, got {actual_dec or '?'})"
            )

        pending = report.get("pending") or []
        if pending:
            detail_parts.append(f"pending:{','.join(pending)}")

        detail = " | ".join(detail_parts)
        v = f"  {' · '.join(verdict)}" if verdict else ""
        print(f"[{rid}] {detail}{v}")

    print("\n--- Summary ---")
    print(f"samples: {len(rows)}")
    if errors:
        print(f"errors:  {errors}")

    def _pct(correct: int, total: int) -> str:
        return f"{correct}/{total} ({correct / total:.0%})" if total else ""

    pairs = [
        ("sponsors acc", "sponsors_correct", "sponsors_total", "sponsors_unknown"),
        ("priority acc (role P-tier)", "priority_correct", "priority_total", "priority_unknown"),
        ("track_id acc", "track_correct", "track_total", "track_unknown"),
        ("location tier acc", "location_correct", "location_total", "location_unknown"),
        ("company tier acc", "company_correct", "company_total", "company_unknown"),
        ("resume fit band acc", "fit_correct", "fit_total", "fit_unknown"),
        ("decision acc (LLM verdict)", "decision_correct", "decision_total", "decision_unknown"),
    ]
    for label, ck, tk, uk in pairs:
        total = counters[tk]
        if total:
            print(f"{label}: {_pct(counters[ck], total)}")
        if counters[uk]:
            print(f"  {label.split(' acc')[0]} unknown (skipped): {counters[uk]}")

    print("\nLabeling guide: evals/golden_set/README.md")
    print("Thresholds: docs/FIT_THRESHOLDS.md")


if __name__ == "__main__":
    main()
