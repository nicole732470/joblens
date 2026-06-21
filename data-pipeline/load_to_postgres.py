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


def rebuild_default_company_groups(cur) -> None:
    """Create a conservative 1:1 company-group mapping for every FEIN.

    This keeps the existing FEIN-keyed sponsorship lookup unchanged while giving
    newer JobPush features an optional company-group layer to attach websites/career URLs
    to. Parent/brand consolidation can later merge multiple FEINs into one
    company group without changing the old sponsorship API.
    """

    cur.execute(
        """
        INSERT INTO company_groups (group_key, canonical_name, display_name)
        SELECT 'legal:' || fein, name, name
        FROM companies
        ON CONFLICT (group_key) DO UPDATE
        SET canonical_name = EXCLUDED.canonical_name,
            display_name = COALESCE(company_groups.display_name, EXCLUDED.display_name),
            updated_at = now()
        """
    )


def upsert_companies(cur, employers: list[dict]) -> None:
    cur.execute(
        """
        CREATE TEMP TABLE tmp_companies (
            fein TEXT,
            name TEXT,
            naics_code TEXT,
            naics_sector TEXT,
            city TEXT,
            state TEXT,
            lca_count INTEGER,
            h1b_count INTEGER,
            certified_count INTEGER,
            top_jobs JSONB
        ) ON COMMIT DROP
        """
    )
    with cur.copy(
        "COPY tmp_companies (fein, name, naics_code, naics_sector, city, "
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
    cur.execute(
        """
        UPDATE companies
        SET lca_count = 0,
            h1b_count = 0,
            certified_count = 0,
            top_jobs = '[]'::jsonb
        """
    )
    cur.execute(
        """
        INSERT INTO companies (
            fein, name, naics_code, naics_sector, city, state,
            lca_count, h1b_count, certified_count, top_jobs
        )
        SELECT
            fein, name, naics_code, naics_sector, city, state,
            lca_count, h1b_count, certified_count, top_jobs
        FROM tmp_companies
        ON CONFLICT (fein) DO UPDATE
        SET name = EXCLUDED.name,
            naics_code = EXCLUDED.naics_code,
            naics_sector = EXCLUDED.naics_sector,
            city = EXCLUDED.city,
            state = EXCLUDED.state,
            lca_count = EXCLUDED.lca_count,
            h1b_count = EXCLUDED.h1b_count,
            certified_count = EXCLUDED.certified_count,
            top_jobs = EXCLUDED.top_jobs
        """
    )
    cur.execute(
        """
        INSERT INTO company_group_companies (company_group_id, fein, relationship, is_primary)
        SELECT g.company_group_id, c.fein, 'legal_entity', TRUE
        FROM companies c
        JOIN company_groups g ON g.group_key = 'legal:' || c.fein
        ON CONFLICT (company_group_id, fein) DO UPDATE
        SET company_group_id = EXCLUDED.company_group_id,
            relationship = EXCLUDED.relationship,
            is_primary = EXCLUDED.is_primary,
            updated_at = now()
        """
    )


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

            print("Clearing replaceable lookup rows")
            cur.execute("TRUNCATE company_aliases RESTART IDENTITY")
            cur.execute("TRUNCATE company_search_keys")

            print("Upserting companies")
            upsert_companies(cur, employers)

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

            print("Rebuilding default company groups")
            rebuild_default_company_groups(cur)

        conn.commit()

        with conn.cursor() as cur:
            counts = {}
            for table in (
                "companies",
                "company_aliases",
                "company_search_keys",
                "company_groups",
                "company_group_companies",
            ):
                cur.execute(f"SELECT count(*) FROM {table}")
                counts[table] = cur.fetchone()[0]

    print(f"Done in {time.time() - t0:.1f}s")
    for table, n in counts.items():
        print(f"  {table}: {n:,} rows")


if __name__ == "__main__":
    main()
