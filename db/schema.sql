-- Takshashila chatbot — v1 schema.
-- Applied automatically on a fresh `make up` (mounted into the init dir), or to a
-- running DB with `make migrate`. Idempotent (IF NOT EXISTS).
--
-- Covers what the current adapters read/write (kb_chunks, leads) plus the
-- structured date tables and the identity-free question log. Content versioning
-- and dashboard aggregate tables arrive with their respective increments.

CREATE EXTENSION IF NOT EXISTS vector;

-- Retrieval corpus. `embedding` dimension MUST match the embedding model
-- (BGE-M3 = 1024). Only published chunks are ever retrieved.
CREATE TABLE IF NOT EXISTS kb_chunks (
    chunk_id     TEXT PRIMARY KEY,
    document_id  TEXT NOT NULL,
    chunk_text   TEXT NOT NULL,
    topic        TEXT NOT NULL,
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding    vector(1024) NOT NULL,
    published    BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS kb_chunks_embedding_idx
    ON kb_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS kb_chunks_published_idx ON kb_chunks (published);
CREATE INDEX IF NOT EXISTS kb_chunks_document_id_idx ON kb_chunks (document_id);

-- Editable content documents. Only the published columns are ever served; drafts
-- are staged until Publish (US-8). Publishing snapshots the body into _versions.
CREATE TABLE IF NOT EXISTS kb_documents (
    id                TEXT PRIMARY KEY,
    topic             TEXT NOT NULL,
    title             TEXT NOT NULL,
    draft_body        TEXT NOT NULL,
    published_body    TEXT,
    published_version INT NOT NULL DEFAULT 0,
    last_updated      TIMESTAMPTZ,
    metadata          JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS kb_document_versions (
    id           BIGSERIAL PRIMARY KEY,
    document_id  TEXT NOT NULL REFERENCES kb_documents(id),
    version      INT NOT NULL,
    body         TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL
);

-- Structured fee data — status (upcoming/due/overdue) is computed at query time.
CREATE TABLE IF NOT EXISTS fee_items (
    id          BIGSERIAL PRIMARY KEY,
    program     TEXT NOT NULL,
    amount_inr  NUMERIC(12, 2) NOT NULL,
    due_date    DATE NOT NULL,
    currency    TEXT NOT NULL DEFAULT 'INR',
    notes       TEXT
);

-- Structured admission windows — open/closed computed at query time (inclusive close).
CREATE TABLE IF NOT EXISTS admission_windows (
    id           BIGSERIAL PRIMARY KEY,
    program      TEXT NOT NULL,
    intake_label TEXT,
    open_date    DATE NOT NULL,
    close_date   DATE NOT NULL,
    notes        TEXT
);

-- Consented leads. Source of truth for the dashboard; delivery is async (outbox).
CREATE TABLE IF NOT EXISTS leads (
    id                  BIGSERIAL PRIMARY KEY,
    name                TEXT NOT NULL,
    email               TEXT,
    phone               TEXT,
    program             TEXT,
    message             TEXT,
    dead_end_question   TEXT,
    created_at          TIMESTAMPTZ NOT NULL,
    delivery_status     TEXT NOT NULL DEFAULT 'pending',
    delivery_attempts   INT NOT NULL DEFAULT 0,
    last_delivery_error TEXT
);
CREATE INDEX IF NOT EXISTS leads_created_at_idx ON leads (created_at DESC);

-- Durable email outbox — the retryable handoff for lead notifications (EC-18).
-- A row stays pending/failed (retry-eligible) until finally sent, so a consented
-- lead's notification is never lost across restarts/replicas.
CREATE TABLE IF NOT EXISTS outbox (
    id          BIGSERIAL PRIMARY KEY,
    recipient   TEXT NOT NULL,
    subject     TEXT NOT NULL,
    body        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    attempts    INT NOT NULL DEFAULT 0,
    last_error  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS outbox_status_idx ON outbox (status);

-- Question log — NO visitor identity (FR-18, NFR-6); purged at 12 months.
CREATE TABLE IF NOT EXISTS question_logs (
    id            BIGSERIAL PRIMARY KEY,
    question_text TEXT NOT NULL,
    outcome       TEXT NOT NULL,   -- answered | dead_end
    topic         TEXT,
    detected_lang TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS question_logs_created_at_idx ON question_logs (created_at);

-- Dead-end clusters — knowledge-gap backlog for the admin dashboard (AC-9.1).
-- Rebuilt by the clustering worker (replace-all); ranked by frequency.
CREATE TABLE IF NOT EXISTS dead_end_clusters (
    id                  BIGSERIAL PRIMARY KEY,
    representative_text TEXT NOT NULL,
    frequency           INT NOT NULL
);
CREATE INDEX IF NOT EXISTS dead_end_clusters_frequency_idx
    ON dead_end_clusters (frequency DESC);
