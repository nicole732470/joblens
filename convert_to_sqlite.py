#!/usr/bin/env python3
"""
Convert LCA Disclosure Excel file to SQLite for fast querying.

Imports H-1B filings only (excludes E-3 Australian, H-1B1 Chile/Singapore).

Usage:
    python3 convert_to_sqlite.py
"""

VISA_CLASS_FILTER = "H-1B"

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from python_calamine import CalamineWorkbook

BASE_DIR = Path(__file__).resolve().parent
XLSX_PATH = BASE_DIR / "LCA_Dislclosure_Data_FY2026_Q2.xlsx"
DB_PATH = BASE_DIR / "lca_fy2026_q2.db"
BATCH_SIZE = 10_000

# Columns we index for common filters / joins
INDEXED_COLUMNS = [
    "CASE_NUMBER",
    "CASE_STATUS",
    "RECEIVED_DATE",
    "DECISION_DATE",
    "VISA_CLASS",
    "EMPLOYER_NAME",
    "EMPLOYER_STATE",
    "WORKSITE_STATE",
    "SOC_CODE",
    "SOC_TITLE",
    "JOB_TITLE",
    "WAGE_RATE_OF_PAY_FROM",
    "PW_WAGE_LEVEL",
]


def sanitize(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value != value:  # NaN
        return None
    text = str(value).strip()
    return text if text else None


def create_table(conn: sqlite3.Connection, columns: list[str]) -> None:
    col_defs = ", ".join(f'"{col}" TEXT' for col in columns)
    conn.execute(f'CREATE TABLE lca_cases ({col_defs})')


def insert_batches(
    conn: sqlite3.Connection, columns: list[str], rows: list[list[object]]
) -> int:
    placeholders = ", ".join("?" for _ in columns)
    col_list = ", ".join(f'"{col}"' for col in columns)
    sql = f"INSERT INTO lca_cases ({col_list}) VALUES ({placeholders})"

    total = 0
    batch: list[tuple[str | None, ...]] = []
    for row in rows:
        batch.append(tuple(sanitize(v) for v in row))
        if len(batch) >= BATCH_SIZE:
            conn.executemany(sql, batch)
            total += len(batch)
            batch.clear()
            print(f"  inserted {total:,} rows...", flush=True)

    if batch:
        conn.executemany(sql, batch)
        total += len(batch)

    return total


def create_indexes(conn: sqlite3.Connection) -> None:
    for col in INDEXED_COLUMNS:
        idx_name = f"idx_lca_{col.lower()}"
        print(f"  creating index {idx_name}...", flush=True)
        conn.execute(f'CREATE INDEX IF NOT EXISTS {idx_name} ON lca_cases ("{col}")')


def create_metadata(conn: sqlite3.Connection, row_count: int, columns: list[str]) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS _metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    meta = {
        "source_file": XLSX_PATH.name,
        "converted_at_utc": datetime.now(timezone.utc).isoformat(),
        "row_count": str(row_count),
        "column_count": str(len(columns)),
        "columns_json": ",".join(columns),
        "visa_class_filter": VISA_CLASS_FILTER,
    }
    conn.executemany(
        "INSERT OR REPLACE INTO _metadata (key, value) VALUES (?, ?)",
        list(meta.items()),
    )


def create_summary_tables(conn: sqlite3.Connection) -> None:
    summaries = {
        "summary_by_status": """
            CREATE TABLE summary_by_status AS
            SELECT CASE_STATUS AS status, COUNT(*) AS case_count
            FROM lca_cases
            GROUP BY CASE_STATUS
            ORDER BY case_count DESC
        """,
        "summary_by_visa_class": """
            CREATE TABLE summary_by_visa_class AS
            SELECT VISA_CLASS AS visa_class, COUNT(*) AS case_count
            FROM lca_cases
            GROUP BY VISA_CLASS
            ORDER BY case_count DESC
        """,
        "summary_by_worksite_state": """
            CREATE TABLE summary_by_worksite_state AS
            SELECT WORKSITE_STATE AS state, COUNT(*) AS case_count
            FROM lca_cases
            GROUP BY WORKSITE_STATE
            ORDER BY case_count DESC
        """,
        "summary_by_employer_state": """
            CREATE TABLE summary_by_employer_state AS
            SELECT EMPLOYER_STATE AS state, COUNT(*) AS case_count
            FROM lca_cases
            GROUP BY EMPLOYER_STATE
            ORDER BY case_count DESC
        """,
        "summary_top_employers": """
            CREATE TABLE summary_top_employers AS
            SELECT
                EMPLOYER_NAME AS employer_name,
                COUNT(*) AS case_count,
                SUM(CAST(TOTAL_WORKER_POSITIONS AS INTEGER)) AS total_positions
            FROM lca_cases
            WHERE EMPLOYER_NAME IS NOT NULL AND EMPLOYER_NAME != ''
            GROUP BY EMPLOYER_NAME
            ORDER BY case_count DESC
            LIMIT 500
        """,
        "summary_top_soc": """
            CREATE TABLE summary_top_soc AS
            SELECT
                SOC_CODE AS soc_code,
                SOC_TITLE AS soc_title,
                COUNT(*) AS case_count
            FROM lca_cases
            WHERE SOC_CODE IS NOT NULL AND SOC_CODE != ''
            GROUP BY SOC_CODE, SOC_TITLE
            ORDER BY case_count DESC
            LIMIT 200
        """,
        "summary_wage_by_level": """
            CREATE TABLE summary_wage_by_level AS
            SELECT
                PW_WAGE_LEVEL AS wage_level,
                COUNT(*) AS case_count,
                AVG(CAST(WAGE_RATE_OF_PAY_FROM AS REAL)) AS avg_wage_from,
                MIN(CAST(WAGE_RATE_OF_PAY_FROM AS REAL)) AS min_wage_from,
                MAX(CAST(WAGE_RATE_OF_PAY_FROM AS REAL)) AS max_wage_from
            FROM lca_cases
            WHERE WAGE_RATE_OF_PAY_FROM IS NOT NULL
              AND WAGE_RATE_OF_PAY_FROM != ''
              AND CAST(WAGE_RATE_OF_PAY_FROM AS REAL) > 0
            GROUP BY PW_WAGE_LEVEL
            ORDER BY wage_level
        """,
    }

    for name, sql in summaries.items():
        print(f"  building {name}...", flush=True)
        conn.execute(f"DROP TABLE IF EXISTS {name}")
        conn.execute(sql)


def main() -> None:
    if not XLSX_PATH.exists():
        raise FileNotFoundError(f"Missing source file: {XLSX_PATH}")

    if DB_PATH.exists():
        DB_PATH.unlink()

    t0 = time.time()
    print(f"Reading {XLSX_PATH.name} with calamine...", flush=True)
    wb = CalamineWorkbook.from_path(str(XLSX_PATH))
    sheet = wb.get_sheet_by_index(0)
    data = sheet.to_python()
    headers = [str(h) for h in data[0]]
    visa_idx = headers.index("VISA_CLASS")
    all_rows = data[1:]
    rows = [r for r in all_rows if sanitize(r[visa_idx]) == VISA_CLASS_FILTER]
    skipped = len(all_rows) - len(rows)
    print(
        f"Loaded {len(all_rows):,} rows x {len(headers)} columns in {time.time() - t0:.1f}s",
        flush=True,
    )
    print(f"Keeping {len(rows):,} {VISA_CLASS_FILTER} rows (skipped {skipped:,} other visa classes)", flush=True)

    t1 = time.time()
    print(f"Writing SQLite database to {DB_PATH.name}...", flush=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA temp_store = MEMORY")

    create_table(conn, headers)
    row_count = insert_batches(conn, headers, rows)
    conn.commit()
    print(f"Inserted {row_count:,} rows in {time.time() - t1:.1f}s")

    t2 = time.time()
    print("Creating indexes...", flush=True)
    create_indexes(conn)
    conn.commit()
    print(f"Indexes created in {time.time() - t2:.1f}s")

    t3 = time.time()
    print("Building summary tables...", flush=True)
    create_metadata(conn, row_count, headers)
    create_summary_tables(conn)
    conn.commit()
    print(f"Summary tables built in {time.time() - t3:.1f}s")

    # Useful views for quick exploration
    conn.executescript(
        """
        CREATE VIEW IF NOT EXISTS v_certified AS
        SELECT * FROM lca_cases WHERE CASE_STATUS = 'Certified';
        """
    )
    conn.commit()
    conn.close()

    db_size_mb = DB_PATH.stat().st_size / 1024 / 1024
    print(f"\nDone in {time.time() - t0:.1f}s total")
    print(f"Database: {DB_PATH}")
    print(f"Size: {db_size_mb:.1f} MB")
    print(f"Rows: {row_count:,}")
    print(f"\nNext: python3 export_employer_index.py")


if __name__ == "__main__":
    main()
