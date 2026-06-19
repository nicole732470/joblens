-- Run once against RDS after creating the joblens database.
-- psql "$DATABASE_URL" -f deploy/rds-init.sql

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS resume_chunks (
    id          TEXT PRIMARY KEY,
    resume_key  TEXT NOT NULL DEFAULT 'default',
    section     TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL,
    embedding   vector(1536),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_resume_chunks_key ON resume_chunks(resume_key);
