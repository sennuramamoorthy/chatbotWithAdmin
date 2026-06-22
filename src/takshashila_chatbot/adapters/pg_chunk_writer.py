"""Postgres chunk writer — the re-index side of publishing (US-8, AC-8.2).

Replaces a document's published chunks in ``kb_chunks`` with freshly embedded ones
(``published = TRUE``). The PgVectorRetriever reads the same table, so published
content becomes answerable.
"""

from __future__ import annotations

import json

from ..application.content_service import ChunkToWrite
from .db import Executor
from .pgvector_retriever import to_vector_literal

_DELETE_SQL = "DELETE FROM kb_chunks WHERE document_id = %s"
_INSERT_SQL = """
INSERT INTO kb_chunks (chunk_id, document_id, chunk_text, topic, metadata, embedding, published)
VALUES (%s, %s, %s, %s, %s::jsonb, %s::vector, TRUE)
"""


class PgChunkWriter:
    def __init__(self, executor: Executor) -> None:
        self._executor = executor

    def replace_document_chunks(self, document_id: str, chunks: list[ChunkToWrite]) -> None:
        self._executor.execute(_DELETE_SQL, (document_id,))
        for index, chunk in enumerate(chunks):
            self._executor.execute(
                _INSERT_SQL,
                (
                    f"{document_id}-{index}",
                    document_id,
                    chunk.text,
                    chunk.topic,
                    json.dumps(dict(chunk.metadata)),
                    to_vector_literal(chunk.embedding),
                ),
            )
