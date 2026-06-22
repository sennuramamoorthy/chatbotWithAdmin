"""Postgres content repository — documents + immutable published versions (US-8).

Drafts are upserted into ``kb_documents``; publishing updates the published columns
and snapshots the body into ``kb_document_versions`` (so only the published state is
ever served, and history is retained).
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Sequence

from ..application.content_service import Document
from .db import Executor

_GET_SQL = """
SELECT id, topic, title, draft_body, published_body, published_version, last_updated, metadata
FROM kb_documents WHERE id = %s
"""
_UPSERT_SQL = """
INSERT INTO kb_documents (id, topic, title, draft_body, metadata)
VALUES (%s, %s, %s, %s, %s::jsonb)
ON CONFLICT (id) DO UPDATE SET
    topic = EXCLUDED.topic, title = EXCLUDED.title,
    draft_body = EXCLUDED.draft_body, metadata = EXCLUDED.metadata
RETURNING id, topic, title, draft_body, published_body, published_version, last_updated, metadata
"""
_PUBLISH_SQL = """
UPDATE kb_documents SET published_body = %s, published_version = %s, last_updated = %s
WHERE id = %s
RETURNING id, topic, title, draft_body, published_body, published_version, last_updated, metadata
"""
_VERSION_SQL = """
INSERT INTO kb_document_versions (document_id, version, body, published_at)
VALUES (%s, %s, %s, %s)
"""


def _to_document(row: Sequence) -> Document:
    metadata = row[7]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    return Document(
        id=row[0],
        topic=row[1],
        title=row[2],
        draft_body=row[3],
        published_body=row[4],
        published_version=row[5],
        last_updated=row[6],
        metadata=metadata or {},
    )


class PgContentRepository:
    def __init__(self, executor: Executor) -> None:
        self._executor = executor

    def get(self, doc_id: str) -> Document | None:
        rows = self._executor.execute(_GET_SQL, (doc_id,))
        return _to_document(rows[0]) if rows else None

    def save_draft(self, doc_id, *, topic, title, body, metadata) -> Document:
        rows = self._executor.execute(
            _UPSERT_SQL, (doc_id, topic, title, body, json.dumps(dict(metadata)))
        )
        return _to_document(rows[0])

    def mark_published(self, doc_id, *, version, body, published_at: dt.datetime) -> Document:
        rows = self._executor.execute(_PUBLISH_SQL, (body, version, published_at, doc_id))
        self._executor.execute(_VERSION_SQL, (doc_id, version, body, published_at))
        return _to_document(rows[0])
