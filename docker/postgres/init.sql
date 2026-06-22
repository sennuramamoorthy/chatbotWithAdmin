-- Runs once on first container start (empty data volume).
-- Enables pgvector so kb_chunks.embedding can be indexed for retrieval
-- (see docs/system-design.md §4.1).
CREATE EXTENSION IF NOT EXISTS vector;
