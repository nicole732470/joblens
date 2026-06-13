#!/usr/bin/env python3
"""Export national H-1B employer summary (all FEINs) with networking columns — no website."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from naics_sectors import naics_sector_label
from networking_connects import ALL_EMPLOYERS_PATH, load_connects

DB_PATH = Path(__file__).resolve().parent / "lca_fy2026_q2.db"
DATA_DIR = Path(__file__).resolve().parent / "data"

FIELDNAMES = [
    "fein",
    "employer_name",
    "lca_count",
    "certified_count",
    "h1b_count",
    "city",
    "state",
    "worksite_states",
    "cook_county_lca",
    "naics_code",
    "naics_sector",
    "connect_status",
    "connect_sent_date",
    "connect_notes",
]


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


def export_all(conn: sqlite3.Connection) -> Path:
    naics_by_fein = fetch_naics_by_fein(conn)
    connects = load_connects()

    cur = conn.execute(
        """
        SELECT
            EMPLOYER_FEIN AS fein,
            MIN(EMPLOYER_NAME) AS employer_name,
            COUNT(*) AS lca_count,
            SUM(CASE WHEN CASE_STATUS IN ('Certified', 'Certified - Withdrawn') THEN 1 ELSE 0 END) AS certified_count,
            SUM(CASE WHEN VISA_CLASS = 'H-1B' THEN 1 ELSE 0 END) AS h1b_count,
            MIN(EMPLOYER_CITY) AS city,
            MIN(EMPLOYER_STATE) AS state,
            GROUP_CONCAT(DISTINCT WORKSITE_STATE) AS worksite_states,
            SUM(
                CASE
                    WHEN WORKSITE_STATE = 'IL' AND WORKSITE_COUNTY = 'COOK' THEN 1
                    ELSE 0
                END
            ) AS cook_county_lca
        FROM lca_cases
        GROUP BY EMPLOYER_FEIN
        ORDER BY lca_count DESC
        """
    )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rows_written = 0
    with ALL_EMPLOYERS_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in cur:
            fein = row[0]
            naics = naics_by_fein.get(fein, "")
            conn_row = connects.get(fein, {})
            writer.writerow(
                {
                    "fein": fein,
                    "employer_name": row[1],
                    "lca_count": row[2],
                    "certified_count": row[3],
                    "h1b_count": row[4],
                    "city": row[5] or "",
                    "state": row[6] or "",
                    "worksite_states": row[7] or "",
                    "cook_county_lca": row[8],
                    "naics_code": naics,
                    "naics_sector": naics_sector_label(naics),
                    "connect_status": conn_row.get("status", ""),
                    "connect_sent_date": conn_row.get("sent_date", ""),
                    "connect_notes": conn_row.get("notes", ""),
                }
            )
            rows_written += 1

    return ALL_EMPLOYERS_PATH, rows_written


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Missing database: {DB_PATH}. Run convert_to_sqlite.py first.")

    conn = sqlite3.connect(DB_PATH)
    try:
        out, n = export_all(conn)
    finally:
        conn.close()

    marked = sum(1 for _ in open(out, encoding="utf-8"))  # recount with connect
    connects = load_connects()
    print(f"Wrote {out} ({n:,} employers)")
    print(f"  Networking log: {len(connects)} FEIN(s), {sum(1 for c in connects.values() if c.get('status'))} with status")


if __name__ == "__main__":
    main()
