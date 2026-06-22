"""Edge adapters — concrete implementations of the application ports.

HTTP adapters (self-hosted LLM, embeddings) take an injected ``httpx.Client`` so
they are tested with ``httpx.MockTransport``. Postgres adapters take an injected
``Executor`` (a thin SQL seam) so the SQL + row-mapping is tested with a recording
fake; production supplies a psycopg-backed executor.
"""
