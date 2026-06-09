#!/usr/bin/env python3
"""Add official website column to cook_county_companies.csv via Clearbit suggest API."""

from __future__ import annotations

import csv
import json
import re
import subprocess
import time
import urllib.parse
from pathlib import Path

BASE_DIR = Path(__file__).parent
CSV_PATH = BASE_DIR / "data" / "cook_county_companies.csv"
CACHE_PATH = BASE_DIR / "data" / "cook_county_website_cache.json"

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

# Manual overrides where autocomplete is ambiguous or wrong.
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
    overlap = len(a & b)
    return overlap / max(len(a), len(b))


def clean_queries(employer_name: str) -> list[str]:
    norm = normalize(employer_name)
    words = norm.split()
    queries: list[str] = []
    if norm:
        queries.append(norm)
    if len(words) >= 2:
        queries.append(" ".join(words[:2]))
    if len(words) >= 3:
        queries.append(" ".join(words[:3]))
    if words:
        queries.append(words[0])
    # Deduplicate while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out


def clearbit_suggest(query: str) -> list[dict]:
    url = (
        "https://autocomplete.clearbit.com/v1/companies/suggest?query="
        + urllib.parse.quote(query)
    )
    try:
        raw = subprocess.check_output(
            ["curl", "-s", "--max-time", "8", url],
            text=True,
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


def lookup_website(fein: str, employer_name: str, cache: dict[str, str]) -> str:
    if fein in cache:
        return cache[fein]
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

    website = f"https://{best_domain}" if best_domain and best_score >= 0.25 else ""
    cache[fein] = website
    return website


def load_cache() -> dict[str, str]:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict[str, str]) -> None:
    CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def enrich_csv() -> None:
    cache = load_cache()
    rows: list[dict[str, str]] = []
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        if "website" not in fieldnames:
            fieldnames.append("website")
        for i, row in enumerate(reader, 1):
            fein = row["fein"]
            name = row["employer_name"]
            row["website"] = lookup_website(fein, name, cache)
            rows.append(row)
            if i % 25 == 0:
                save_cache(cache)
                print(f"  {i}/{len(rows)} processed...", flush=True)
            time.sleep(0.08)

    save_cache(cache)
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    filled = sum(1 for r in rows if r.get("website"))
    print(f"Done: {filled}/{len(rows)} companies have websites")


if __name__ == "__main__":
    enrich_csv()
