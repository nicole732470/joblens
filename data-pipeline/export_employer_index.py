#!/usr/bin/env python3
"""
Export employer index from LCA SQLite DB for the Chrome extension.

Usage:
    python3 export_employer_index.py
    python3 export_employer_index.py --test microsoft
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from generic_tokens import GENERIC_TOKENS, MAX_SHORT_TOKEN_COLLISIONS, NOISE_WORDS
from naics_sectors import naics_sector_label

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "lca_fy2026_q2.db"
SLUG_OVERRIDES_PATH = BASE_DIR / "slug_overrides.json"
OUT_DIR = BASE_DIR.parent / "extension" / "data"
OUT_JSON = OUT_DIR / "employers.json"
OUT_GZ = OUT_DIR / "employers.json.gz"

def tokenize_raw(text: str) -> list[str]:
    text = text.lower().strip()
    text = text.replace("&", " and ")
    text = re.sub(r"[^\w\s-]", " ", text)
    text = text.replace("-", " ")
    return [t for t in re.sub(r"\s+", " ", text).strip().split() if t]


def strip_noise_tokens(tokens: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(tokens):
        if tokens[i] == "north" and i + 1 < len(tokens) and tokens[i + 1] == "america":
            i += 2
            continue
        if tokens[i] not in NOISE_WORDS:
            out.append(tokens[i])
        i += 1
    return out


def meaningful_tokens(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for token in strip_noise_tokens(tokenize_raw(text)):
        if len(token) < 3 or token in GENERIC_TOKENS or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def normalize(text: str) -> str:
    return " ".join(meaningful_tokens(text))


def slugify(text: str) -> str:
    text = normalize(text)
    return re.sub(r"\s+", "-", text)


def slugify_raw(text: str) -> str:
    """Hyphenated slug from display name before legal-suffix stripping."""
    text = text.lower().strip()
    text = text.replace("&", " and ")
    text = re.sub(r"[^\w\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+", "-", text)


def brand_tokens_from_raw(raw: str) -> set[str]:
    """Candidate short brand tokens (ornua, coforge) from a legal name."""
    found: set[str] = set()
    raw_slug = slugify_raw(raw)
    parts = [p for p in raw_slug.split("-") if p]
    if len(parts) >= 2:
        lead = parts[0]
        if len(lead) >= 4 and lead not in GENERIC_TOKENS:
            found.add(lead)
    norm = normalize(raw)
    if not norm or len(norm) < 4:
        return found
    n_parts = norm.split()
    if n_parts[0] not in GENERIC_TOKENS and len(n_parts[0]) >= 4:
        if len(n_parts) >= 2 or len(n_parts[0]) >= 5:
            found.add(n_parts[0])
    return found


def compute_token_collision_counts(all_names: list[list[str]]) -> dict[str, int]:
    from collections import Counter

    counts: Counter[str] = Counter()
    for names in all_names:
        seen: set[str] = set()
        for raw in names:
            for token in brand_tokens_from_raw(raw):
                if token not in seen:
                    counts[token] += 1
                    seen.add(token)
    return dict(counts)


def search_keys_for(name: str, all_names: list[str], token_counts: dict[str, int]) -> list[str]:
    """Build lookup keys — multi-word names always; short brand tokens if low collision."""
    keys: set[str] = set()
    for raw in {name, *all_names}:
        raw_slug = slugify_raw(raw)
        if raw_slug.count("-") >= 1:
            keys.add(raw_slug)

        norm = normalize(raw)
        if not norm or len(norm) < 4:
            continue
        if len(norm.split()) >= 2:
            keys.add(norm)
            slug = slugify(raw)
            if slug.count("-") >= 1:
                keys.add(slug)

        for token in brand_tokens_from_raw(raw):
            if token_counts.get(token, 99) <= MAX_SHORT_TOKEN_COLLISIONS:
                keys.add(token)

    return sorted(keys)


def load_slug_overrides() -> dict[str, str]:
    if not SLUG_OVERRIDES_PATH.exists():
        return {}
    data = json.loads(SLUG_OVERRIDES_PATH.read_text(encoding="utf-8"))
    return {k.lower(): v for k, v in data.items()}


def fetch_top_jobs(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Fetch top 3 jobs per FEIN in one pass."""
    rows = conn.execute(
        """
        WITH ranked AS (
            SELECT
                EMPLOYER_FEIN AS fein,
                JOB_TITLE,
                PW_WAGE_LEVEL,
                WAGE_RATE_OF_PAY_FROM,
                COUNT(*) AS cnt,
                ROW_NUMBER() OVER (
                    PARTITION BY EMPLOYER_FEIN
                    ORDER BY COUNT(*) DESC
                ) AS rn
            FROM lca_cases
            GROUP BY EMPLOYER_FEIN, JOB_TITLE, PW_WAGE_LEVEL, WAGE_RATE_OF_PAY_FROM
        )
        SELECT fein, JOB_TITLE, PW_WAGE_LEVEL, WAGE_RATE_OF_PAY_FROM, cnt
        FROM ranked
        WHERE rn <= 3
        ORDER BY fein, rn
        """
    ).fetchall()

    jobs_by_fein: dict[str, list[dict]] = {}
    for fein, title, level, wage, cnt in rows:
        jobs_by_fein.setdefault(fein, []).append(
            {"title": title, "level": level, "wage_from": wage, "count": cnt}
        )
    return jobs_by_fein


def fetch_naics_by_fein(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute(
        """
        WITH ranked AS (
            SELECT
                EMPLOYER_FEIN AS fein,
                NAICS_CODE AS naics,
                COUNT(*) AS cnt,
                ROW_NUMBER() OVER (
                    PARTITION BY EMPLOYER_FEIN
                    ORDER BY COUNT(*) DESC
                ) AS rn
            FROM lca_cases
            WHERE NAICS_CODE IS NOT NULL AND TRIM(NAICS_CODE) != ''
            GROUP BY EMPLOYER_FEIN, NAICS_CODE
        )
        SELECT fein, naics FROM ranked WHERE rn = 1
        """
    ).fetchall()
    return {fein: naics for fein, naics in rows}


def fetch_employers(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            EMPLOYER_FEIN AS fein,
            MIN(EMPLOYER_NAME) AS primary_name,
            GROUP_CONCAT(DISTINCT EMPLOYER_NAME) AS all_names_csv,
            COUNT(*) AS lca_count,
            SUM(CASE WHEN VISA_CLASS = 'H-1B' THEN 1 ELSE 0 END) AS h1b_count,
            SUM(CASE WHEN CASE_STATUS = 'Certified' THEN 1 ELSE 0 END) AS certified_count,
            MIN(EMPLOYER_CITY) AS city,
            MIN(EMPLOYER_STATE) AS state
        FROM lca_cases
        GROUP BY EMPLOYER_FEIN
        ORDER BY lca_count DESC
        """
    ).fetchall()

    jobs_by_fein = fetch_top_jobs(conn)
    naics_by_fein = fetch_naics_by_fein(conn)
    raw_employers: list[dict] = []
    for row in rows:
        fein, primary_name, names_csv, lca, h1b, certified, city, state = row
        all_names = sorted({n.strip() for n in (names_csv or "").split(",") if n.strip()})
        if primary_name not in all_names:
            all_names.insert(0, primary_name)
        raw_employers.append(
            {
                "fein": fein,
                "name": primary_name,
                "names": all_names,
                "lca_count": lca,
                "h1b_count": h1b,
                "certified_count": certified,
                "city": city,
                "state": state,
                "naics_code": naics_by_fein.get(fein, ""),
                "top_jobs": jobs_by_fein.get(fein, []),
            }
        )

    token_counts = compute_token_collision_counts([e["names"] for e in raw_employers])
    employers: list[dict] = []
    for emp in raw_employers:
        employers.append(
            {
                **emp,
                "naics_sector": naics_sector_label(emp["naics_code"]),
                "search_keys": search_keys_for(emp["name"], emp["names"], token_counts),
            }
        )
    return employers


def build_index(employers: list[dict]) -> dict[str, dict]:
    """Map normalized search key -> best employer (highest lca_count wins)."""
    index: dict[str, dict] = {}
    for emp in employers:
        for key in emp["search_keys"]:
            existing = index.get(key)
            if existing is None or emp["lca_count"] > existing["lca_count"]:
                index[key] = emp
    return index


def lookup(index: dict[str, dict], overrides: dict[str, str], slug: str, h1: str | None = None) -> dict | None:
    slug = slug.lower().strip("/")
    if slug in overrides:
        fein = overrides[slug]
        return next((e for e in index.values() if e["fein"] == fein), None)

    candidates = [
        slug,
        slug.replace("-", " "),
        normalize(slug.replace("-", " ")),
    ]
    if h1:
        candidates.extend([normalize(h1), slugify(h1)])

    seen: set[str] = set()
    best: dict | None = None
    for key in candidates:
        if not key or key in seen:
            continue
        seen.add(key)
        hit = index.get(key)
        if hit and (best is None or hit["lca_count"] > best["lca_count"]):
            best = hit

    return best


def export() -> Path:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Missing database: {DB_PATH}. Run convert_to_sqlite.py first.")

    t0 = time.time()
    conn = sqlite3.connect(DB_PATH)
    employers = fetch_employers(conn)
    meta_row = conn.execute("SELECT value FROM _metadata WHERE key='source_file'").fetchone()
    conn.close()

    key_index = build_index(employers)

    payload = {
        "version": "1.3",
        "source_file": meta_row[0] if meta_row else DB_PATH.name,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "employer_count": len(employers),
        "employers": employers,
        "key_index": {k: v["fein"] for k, v in key_index.items()},
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    OUT_JSON.write_text(raw, encoding="utf-8")
    OUT_GZ.write_bytes(gzip.compress(raw.encode("utf-8"), compresslevel=9))

    print(f"Exported {len(employers):,} employers in {time.time() - t0:.1f}s")
    print(f"  JSON:     {OUT_JSON} ({OUT_JSON.stat().st_size / 1024 / 1024:.2f} MB)")
    print(f"  Gzip:     {OUT_GZ} ({OUT_GZ.stat().st_size / 1024 / 1024:.2f} MB)")
    print(f"  Keys:     {len(key_index):,}")
    return OUT_GZ


def main() -> None:
    parser = argparse.ArgumentParser(description="Export LCA employer index for Chrome extension")
    parser.add_argument("--test", metavar="SLUG", help="Test lookup, e.g. microsoft")
    args = parser.parse_args()

    if args.test and OUT_JSON.exists():
        print(f"Using existing index: {OUT_JSON}")
    else:
        export()

    if args.test:
        data = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        fein_map = {e["fein"]: e for e in data["employers"]}
        key_index = {k: fein_map[v] for k, v in data["key_index"].items() if v in fein_map}
        overrides = data.get("slug_overrides", {})
        hit = lookup(key_index, overrides, args.test)
        if hit:
            print(f"\nTest '{args.test}' -> {hit['name']} ({hit['lca_count']} LCA, {hit['h1b_count']} H-1B)")
        else:
            print(f"\nTest '{args.test}' -> NOT FOUND")


if __name__ == "__main__":
    main()
