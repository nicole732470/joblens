#!/usr/bin/env python3
"""Export Cook County IL H-1B LCA records and employer summary (networking columns, no website)."""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

from networking_connects import COOK_COUNTY_PATH, load_connects, sync_connect_columns

DB_PATH = Path(__file__).parent / "lca_fy2026_q2.db"
DATA_DIR = Path(__file__).parent / "data"

WHERE = """
    WORKSITE_STATE = 'IL'
    AND WORKSITE_COUNTY = 'COOK'
"""

FIELDNAMES = [
    "fein",
    "employer_name",
    "lca_count",
    "certified_count",
    "worksite_cities",
    "connect_status",
    "connect_sent_date",
    "connect_notes",
]


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
    out = COOK_COUNTY_PATH
    connects = load_connects()

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

    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in cur:
            fein = row[0]
            conn_row = connects.get(fein, {})
            writer.writerow(
                {
                    "fein": fein,
                    "employer_name": row[1],
                    "lca_count": row[2],
                    "certified_count": row[3],
                    "worksite_cities": row[4] or "",
                    "connect_status": conn_row.get("status", ""),
                    "connect_sent_date": conn_row.get("sent_date", ""),
                    "connect_notes": conn_row.get("notes", ""),
                }
            )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Cook County H-1B LCA data")
    parser.add_argument(
        "--sync-only",
        action="store_true",
        help="Only refresh connect columns in cook_county_companies.csv",
    )
    args = parser.parse_args()

    DATA_DIR.mkdir(exist_ok=True)

    if args.sync_only:
        n = sync_connect_columns(COOK_COUNTY_PATH)
        print(f"Synced {COOK_COUNTY_PATH.name} — {n} marked")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        full = export_full(conn)
        summary = export_summary(conn)
        full_rows = sum(1 for _ in open(full, encoding="utf-8")) - 1
        summary_rows = sum(1 for _ in open(summary, encoding="utf-8")) - 1
        print(f"Wrote {full} ({full_rows:,} rows, all columns)")
        print(f"Wrote {summary} ({summary_rows:,} employers)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
