#!/usr/bin/env python3
"""Export Cook County IL H-1B LCA records and employer summary (with website column)."""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

from cook_county_websites import CSV_PATH, enrich_csv, load_website_map, merge_legacy_cache

DB_PATH = Path(__file__).parent / "lca_fy2026_q2.db"
DATA_DIR = Path(__file__).parent / "data"

WHERE = """
    WORKSITE_STATE = 'IL'
    AND WORKSITE_COUNTY = 'COOK'
"""


def export_full(conn: sqlite3.Connection) -> Path:
    out = DATA_DIR / "cook_county_lca_full.csv"
    cur = conn.execute(f"SELECT * FROM lca_cases WHERE {WHERE} ORDER BY CASE_NUMBER")
    columns = [d[0] for d in cur.description]
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(cur)
    return out


def export_summary(conn: sqlite3.Connection) -> Path:
    out = CSV_PATH
    website_map = merge_legacy_cache(load_website_map(out))

    cur = conn.execute(
        f"""
        SELECT
            EMPLOYER_FEIN AS fein,
            MAX(EMPLOYER_NAME) AS employer_name,
            COUNT(*) AS lca_count,
            SUM(CASE WHEN CASE_STATUS IN ('Certified', 'Certified - Withdrawn') THEN 1 ELSE 0 END) AS certified_count,
            GROUP_CONCAT(DISTINCT WORKSITE_CITY) AS worksite_cities
        FROM lca_cases
        WHERE {WHERE}
        GROUP BY EMPLOYER_FEIN
        ORDER BY lca_count DESC
        """
    )
    columns = [d[0] for d in cur.description] + ["website"]
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in cur:
            writer.writerow([*row, website_map.get(row[0], "")])
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Cook County H-1B LCA data")
    parser.add_argument(
        "--websites",
        action="store_true",
        help="After export, fetch missing official websites into the same CSV",
    )
    parser.add_argument(
        "--websites-only",
        action="store_true",
        help="Only enrich missing website cells in cook_county_companies.csv (no SQL re-export)",
    )
    parser.add_argument(
        "--force-websites",
        action="store_true",
        help="Re-fetch all websites (Clearbit), not just empty cells",
    )
    args = parser.parse_args()

    DATA_DIR.mkdir(exist_ok=True)

    if args.websites_only:
        filled, total = enrich_csv(force=args.force_websites)
        print(f"Updated {CSV_PATH} — {filled}/{total} companies have websites")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        full = export_full(conn)
        summary = export_summary(conn)
        full_rows = sum(1 for _ in open(full, encoding="utf-8")) - 1
        summary_rows = sum(1 for _ in open(summary, encoding="utf-8")) - 1
        print(f"Wrote {full} ({full_rows:,} rows, all columns)")
        print(f"Wrote {summary} ({summary_rows:,} employers, website column preserved)")
    finally:
        conn.close()

    if args.websites or args.force_websites:
        filled, total = enrich_csv(force=args.force_websites)
        print(f"Websites: {filled}/{total} companies have URLs in {CSV_PATH.name}")


if __name__ == "__main__":
    main()
