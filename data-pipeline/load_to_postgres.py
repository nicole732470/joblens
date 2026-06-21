#!/usr/bin/env python3
"""
Load the employer index (`data/h1b/employers.json.gz`) into PostgreSQL.

This is the bridge from the existing offline H-1B pipeline to the new backend.
The shipped gzip index is the source of truth (the raw Excel / SQLite DB are not
committed). Loads into the schema defined in db/schema.sql.

Usage:
    python3 load_to_postgres.py
    DATABASE_URL=postgresql://user:pass@host:5432/db python3 load_to_postgres.py
"""

from __future__ import annotations

import gzip
import json
import os
import time
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
INDEX_PATH = REPO_ROOT / "data" / "h1b" / "employers.json.gz"
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://jobintel:jobintel@localhost:5433/jobintel"
)


def load_index() -> dict:
    with gzip.open(INDEX_PATH, "rt", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    t0 = time.time()
    print(f"Reading index: {INDEX_PATH}")
    index = load_index()
    employers = index["employers"]
    key_index = index.get("key_index", {})
    feins = {e["fein"] for e in employers}
    print(f"  {len(employers):,} employers · {len(key_index):,} search keys")

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            print("Applying schema (db/schema.sql)")
            cur.execute(SCHEMA_PATH.read_text(encoding="utf-8"))

            print("Clearing existing rows")
            cur.execute("TRUNCATE companies RESTART IDENTITY CASCADE")

            print("Loading companies")
            with cur.copy(
                "COPY companies (fein, name, naics_code, naics_sector, city, "
                "state, lca_count, h1b_count, certified_count, top_jobs) "
                "FROM STDIN"
            ) as copy:
                for e in employers:
                    copy.write_row(
                        [
                            e["fein"],
                            e.get("name") or "",
                            e.get("naics_code"),
                            e.get("naics_sector"),
                            e.get("city"),
                            e.get("state"),
                            e.get("lca_count") or 0,
                            e.get("h1b_count") or 0,
                            e.get("certified_count") or 0,
                            Jsonb(e.get("top_jobs") or []),
                        ]
                    )

            print("Loading aliases")
            with cur.copy(
                "COPY company_aliases (fein, alias_name) FROM STDIN"
            ) as copy:
                for e in employers:
                    seen: set[str] = set()
                    for alias in [e.get("name"), *(e.get("names") or [])]:
                        if not alias or alias in seen:
                            continue
                        seen.add(alias)
                        copy.write_row([e["fein"], alias])

            print("Loading search keys")
            with cur.copy(
                "COPY company_search_keys (search_key, fein) FROM STDIN"
            ) as copy:
                for key, fein in key_index.items():
                    if fein in feins:
                        copy.write_row([key, fein])

        conn.commit()

        with conn.cursor() as cur:
            counts = {}
            for table in ("companies", "company_aliases", "company_search_keys"):
                cur.execute(f"SELECT count(*) FROM {table}")
                counts[table] = cur.fetchone()[0]

    print(f"Done in {time.time() - t0:.1f}s")
    for table, n in counts.items():
        print(f"  {table}: {n:,} rows")


if __name__ == "__main__":
    main()
