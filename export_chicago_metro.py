#!/usr/bin/env python3
"""Export full Chicago metro LCA records and employer summary from SQLite."""

import csv
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "lca_fy2026_q2.db"
DATA_DIR = Path(__file__).parent / "data"

CHICAGO_COUNTIES = ("COOK", "DUPAGE", "LAKE", "WILL", "KANE", "MCHENRY")
COUNTY_SQL = ", ".join(f"'{c}'" for c in CHICAGO_COUNTIES)

WHERE = f"""
    WORKSITE_STATE = 'IL'
    AND WORKSITE_COUNTY IN ({COUNTY_SQL})
"""


def export_full(conn: sqlite3.Connection) -> Path:
    out = DATA_DIR / "chicago_metro_lca_full.csv"
    cur = conn.execute(f"SELECT * FROM lca_cases WHERE {WHERE} ORDER BY CASE_NUMBER")
    columns = [d[0] for d in cur.description]
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(cur)
    return out


def export_summary(conn: sqlite3.Connection) -> Path:
    out = DATA_DIR / "chicago_metro_companies.csv"
    cur = conn.execute(
        f"""
        SELECT
            EMPLOYER_FEIN AS fein,
            MAX(EMPLOYER_NAME) AS employer_name,
            COUNT(*) AS lca_count,
            SUM(CASE WHEN CASE_STATUS IN ('Certified', 'Certified - Withdrawn') THEN 1 ELSE 0 END) AS certified_count,
            GROUP_CONCAT(DISTINCT WORKSITE_CITY) AS worksite_cities,
            GROUP_CONCAT(DISTINCT WORKSITE_COUNTY) AS worksite_counties
        FROM lca_cases
        WHERE {WHERE} AND VISA_CLASS = 'H-1B'
        GROUP BY EMPLOYER_FEIN
        ORDER BY lca_count DESC
        """
    )
    columns = [d[0] for d in cur.description]
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(cur)
    return out


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        full = export_full(conn)
        summary = export_summary(conn)
        full_rows = sum(1 for _ in open(full, encoding="utf-8")) - 1
        summary_rows = sum(1 for _ in open(summary, encoding="utf-8")) - 1
        print(f"Wrote {full} ({full_rows:,} rows, all columns)")
        print(f"Wrote {summary} ({summary_rows:,} H-1B employers)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
