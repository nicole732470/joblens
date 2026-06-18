#!/usr/bin/env python3
"""Website lookup for Cook County employer CSV (Clearbit suggest + manual overrides)."""

from __future__ import annotations

import csv
import json
import re
import subprocess
import time
import urllib.parse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "data" / "cook_county_companies.csv"
LEGACY_CACHE_PATH = BASE_DIR / "data" / "cook_county_website_cache.json"

SUFFIXES = (
    " incorporated",
    " corporation",
    " company",
    " limited",
    " llc",
    " inc",
    " corp",
    " ltd",
    " co",
    " llp",
    " lp",
    " plc",
    " usa",
    " us",
    " u s",
)

OVERRIDES: dict[str, str] = {
    "34-6565596": "https://www.ey.com",
    "13-3924155": "https://www.cognizant.com",
    "98-0429806": "https://www.tcs.com",
    "06-1454513": "https://www.deloitte.com",
    "22-2575929": "https://www.capgemini.com",
    "36-2596612": "https://www.medline.com",
    "13-2624428": "https://www.jpmorganchase.com",
    "77-0493581": "https://www.google.com",
    "72-0542904": "https://www.accenture.com",
    "36-2167817": "https://www.northwestern.edu",
    "36-2177139": "https://www.uchicago.edu",
    "37-6000511": "https://www.uic.edu",
    "13-3577870": "https://www.pwc.com",
    "35-2618445": "https://www.themathcompany.com",
    "75-2608565": "https://www.kearney.com",
}


def normalize(text: str) -> str:
    text = text.lower().strip()
    text = text.replace("&", " and ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for suffix in SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return text


def tokens(text: str) -> set[str]:
    return {t for t in normalize(text).split() if len(t) >= 2}


def score_match(employer: str, candidate_name: str) -> float:
    a, b = tokens(employer), tokens(candidate_name)
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a), len(b))


def clean_queries(employer_name: str) -> list[str]:
    norm = normalize(employer_name)
    parts = [employer_name.strip(), norm]
    if norm:
        parts.append(norm.split()[0] if norm.split() else norm)
    seen: set[str] = set()
    out: list[str] = []
    for q in parts:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out


def clearbit_suggest(query: str) -> list[dict]:
    url = "https://autocomplete.clearbit.com/v1/companies/suggest?" + urllib.parse.urlencode(
        {"query": query}
    )
    try:
        raw = subprocess.check_output(
            ["curl", "-sf", "--max-time", "8", url],
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return []
    raw = raw.strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def lookup_website(fein: str, employer_name: str, known: dict[str, str]) -> str:
    if fein in known and known[fein]:
        return known[fein]
    if fein in OVERRIDES:
        return OVERRIDES[fein]

    best_domain = ""
    best_score = 0.0
    for query in clean_queries(employer_name):
        for hit in clearbit_suggest(query):
            domain = (hit.get("domain") or "").strip()
            name = (hit.get("name") or "").strip()
            if not domain:
                continue
            s = score_match(employer_name, name)
            if s > best_score:
                best_score = s
                best_domain = domain
        if best_score >= 0.5:
            break
        time.sleep(0.12)

    return f"https://{best_domain}" if best_domain and best_score >= 0.25 else ""


def load_website_map(csv_path: Path = CSV_PATH) -> dict[str, str]:
    """Load fein → website from the companies CSV (single source of truth)."""
    if not csv_path.exists():
        return {}
    with csv_path.open(newline="", encoding="utf-8") as f:
        return {row["fein"]: row.get("website", "").strip() for row in csv.DictReader(f)}


def merge_legacy_cache(website_map: dict[str, str]) -> dict[str, str]:
    """One-time merge from deprecated cook_county_website_cache.json."""
    if not LEGACY_CACHE_PATH.exists():
        return website_map
    legacy = json.loads(LEGACY_CACHE_PATH.read_text(encoding="utf-8"))
    merged = dict(website_map)
    for fein, url in legacy.items():
        if url and not merged.get(fein):
            merged[fein] = url
    return merged


def enrich_csv(csv_path: Path = CSV_PATH, *, force: bool = False) -> tuple[int, int]:
    """Fill missing website cells in-place. Returns (filled, total)."""
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing {csv_path}. Run export_cook_county.py first.")

    known = merge_legacy_cache(load_website_map(csv_path))
    rows: list[dict[str, str]] = []
    fieldnames: list[str] = []

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        if "website" not in fieldnames:
            fieldnames.append("website")
        for i, row in enumerate(reader, 1):
            fein = row["fein"]
            name = row["employer_name"]
            current = row.get("website", "").strip()
            if force or not current:
                row["website"] = lookup_website(fein, name, known)
                known[fein] = row["website"]
            else:
                known[fein] = current
            rows.append(row)
            if i % 25 == 0:
                _write_csv(csv_path, fieldnames, rows)
                print(f"  {i}/{len(rows)} processed...", flush=True)
            time.sleep(0.08 if (force or not current) else 0)

    _write_csv(csv_path, fieldnames, rows)
    filled = sum(1 for r in rows if r.get("website"))
    return filled, len(rows)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
