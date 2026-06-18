-- H-1B / LCA structured data, loaded from extension/data/employers.json.gz
-- by data-pipeline/load_to_postgres.py. Idempotent (safe to re-run).

CREATE TABLE IF NOT EXISTS companies (
    fein            TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    naics_code      TEXT,
    naics_sector    TEXT,
    city            TEXT,
    state           TEXT,
    lca_count       INTEGER NOT NULL DEFAULT 0,
    h1b_count       INTEGER NOT NULL DEFAULT 0,
    certified_count INTEGER NOT NULL DEFAULT 0,
    top_jobs        JSONB   NOT NULL DEFAULT '[]'::jsonb
);

-- Alternate legal names / brands that resolve to the same FEIN.
CREATE TABLE IF NOT EXISTS company_aliases (
    id         BIGSERIAL PRIMARY KEY,
    fein       TEXT NOT NULL REFERENCES companies(fein) ON DELETE CASCADE,
    alias_name TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_company_aliases_fein ON company_aliases(fein);

-- Collision-aware lookup keys (normalized name/slug/brand token -> FEIN).
CREATE TABLE IF NOT EXISTS company_search_keys (
    search_key TEXT PRIMARY KEY,
    fein       TEXT NOT NULL REFERENCES companies(fein) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_company_search_keys_fein ON company_search_keys(fein);
