"""Content management (US-8): edit drafts, then Publish to re-index live.

Edits update only the draft (not served). Publish snapshots the draft as a new
version, chunks + embeds it, replaces the document's published chunks in the index,
and stamps "last updated" — so only the published state ever goes live (EC-22/23).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from ..domain.clock import Clock
from ..domain.content import chunk_text
from .ports import Embedder


@dataclass(frozen=True)
class Document:
    id: str
    topic: str
    title: str
    draft_body: str
    published_body: str | None = None
    published_version: int = 0
    last_updated: dt.datetime | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ChunkToWrite:
    text: str
    embedding: list[float]
    topic: str
    metadata: Mapping[str, str]


class ContentRepository(Protocol):
    def get(self, doc_id: str) -> Document | None: ...

    def save_draft(
        self, doc_id: str, *, topic: str, title: str, body: str, metadata: Mapping[str, str]
    ) -> Document: ...

    def mark_published(
        self, doc_id: str, *, version: int, body: str, published_at: dt.datetime
    ) -> Document: ...


class ChunkWriter(Protocol):
    def replace_document_chunks(self, document_id: str, chunks: list[ChunkToWrite]) -> None: ...


class ContentService:
    def __init__(
        self,
        repo: ContentRepository,
        chunk_writer: ChunkWriter,
        embedder: Embedder,
        clock: Clock,
    ) -> None:
        self._repo = repo
        self._chunk_writer = chunk_writer
        self._embedder = embedder
        self._clock = clock

    def get(self, doc_id: str) -> Document | None:
        return self._repo.get(doc_id)

    def save_draft(
        self,
        doc_id: str,
        *,
        topic: str,
        title: str,
        body: str,
        metadata: Mapping[str, str] | None = None,
    ) -> Document:
        return self._repo.save_draft(
            doc_id, topic=topic, title=title, body=body, metadata=metadata or {}
        )

    def publish(self, doc_id: str) -> Document:
        doc = self._repo.get(doc_id)
        if doc is None:
            raise KeyError(doc_id)

        chunks = [
            ChunkToWrite(
                text=text,
                embedding=self._embedder.embed(text),
                topic=doc.topic,
                metadata=doc.metadata,
            )
            for text in chunk_text(doc.draft_body)
        ]
        self._chunk_writer.replace_document_chunks(doc_id, chunks)

        return self._repo.mark_published(
            doc_id,
            version=doc.published_version + 1,
            body=doc.draft_body,
            published_at=self._clock.now(),
        )
