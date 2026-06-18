-- Runs once on first container start (empty data volume).
-- Enables the pgvector extension so embedding columns can be created later.
CREATE EXTENSION IF NOT EXISTS vector;
