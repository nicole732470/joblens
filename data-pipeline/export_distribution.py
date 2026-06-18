#!/usr/bin/env python3
"""Regenerate national H-1B distribution CSVs from SQLite."""

import csv
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "lca_fy2026_q2.db"
DATA_DIR = Path(__file__).parent / "data"


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM lca_cases").fetchone()[0]

    jobs = conn.execute(
        """
        SELECT SOC_TITLE, COUNT(*) cnt, ROUND(COUNT(*)*100.0/?, 2) pct
        FROM lca_cases WHERE SOC_TITLE IS NOT NULL
        GROUP BY SOC_TITLE ORDER BY cnt DESC LIMIT 50
        """,
        (total,),
    )
    with (DATA_DIR / "top_jobs_distribution.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["SOC_TITLE", "cnt", "pct"])
        w.writerows(jobs)

    soc = conn.execute(
        """
        SELECT SUBSTR(SOC_CODE,1,2) soc_major,
          CASE SUBSTR(SOC_CODE,1,2)
            WHEN '15' THEN 'Computer & Mathematical'
            WHEN '17' THEN 'Architecture & Engineering'
            WHEN '13' THEN 'Business & Financial'
            WHEN '11' THEN 'Management'
            WHEN '19' THEN 'Life, Physical & Social Science'
            WHEN '29' THEN 'Healthcare Practitioners'
            WHEN '25' THEN 'Education'
            ELSE 'Other'
          END as group_name,
          COUNT(*) cnt, ROUND(COUNT(*)*100.0/?, 2) pct
        FROM lca_cases GROUP BY soc_major ORDER BY cnt DESC
        """,
        (total,),
    )
    with (DATA_DIR / "soc_major_distribution.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["soc_major", "group_name", "cnt", "pct"])
        w.writerows(soc)

    conn.close()
    print(f"Wrote distribution CSVs ({total:,} H-1B rows)")


if __name__ == "__main__":
    main()
