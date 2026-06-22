"""In-memory repository implementations.

Volatile but real (not test-only): used by the dev entrypoint and the test suite.
Durable Postgres adapters live in ``adapters/`` behind the same interfaces.
"""

from __future__ import annotations

import datetime as dt
import math
import string
from dataclasses import replace

from ..domain.clock import Clock
from ..domain.retrieval import RetrievedChunk
from .content_service import ChunkToWrite, Document
from .lead_service import LeadDraft, StoredLead
from .ports import DeadEndGroup, QuestionOutcome, VolumeStats

_STOPWORDS = frozenset(
    {
        "the", "is", "a", "an", "what", "of", "in", "to", "for", "and", "at", "on",
        "my", "i", "are", "when", "where", "how", "do", "does", "you", "please", "today",
    }
)


def _stem(word: str) -> str:
    # Crude singularization so "fees"/"fee", "scholarships"/"scholarship" match.
    # Applied to both query and chunk, so consistency matters more than correctness.
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _keywords(text: str) -> set[str]:
    words = set()
    for raw in text.lower().split():
        word = raw.strip(string.punctuation)
        if word and word not in _STOPWORDS:
            words.add(_stem(word))
    return words


class InMemoryLeadRepository:
    def __init__(self) -> None:
        self._items: list[StoredLead] = []

    def save(self, draft: LeadDraft) -> StoredLead:
        stored = StoredLead(
            id=f"lead-{len(self._items) + 1}",  # deterministic; DB uses a sequence/uuid
            name=draft.name,
            email=draft.email,
            phone=draft.phone,
            program=draft.program,
            message=draft.message,
            dead_end_question=draft.dead_end_question,
            created_at=draft.created_at,
        )
        self._items.append(stored)
        return stored

    def list(self) -> list[StoredLead]:
        return list(self._items)

    def purge_before(self, cutoff: dt.date) -> int:
        before = len(self._items)
        self._items = [item for item in self._items if item.created_at.date() >= cutoff]
        return before - len(self._items)


class InMemoryDeadEndClusterRepository:
    def __init__(self) -> None:
        self._groups: list[DeadEndGroup] = []

    def replace_all(self, groups: list[DeadEndGroup]) -> None:
        self._groups = list(groups)

    def ranked(self, limit: int = 50) -> list[DeadEndGroup]:
        return sorted(self._groups, key=lambda g: g.frequency, reverse=True)[:limit]


class InMemoryQuestionLog:
    """Identity-free question log (FR-18). Implements OutcomeSink + DeadEndLogStore
    + StatsStore + Purger so the demo wiring can use one cohesive object."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._entries: list[dict] = []

    def record(self, outcome: QuestionOutcome) -> None:
        self._entries.append(
            {
                "question": outcome.question,
                "outcome": outcome.outcome,
                "topic": outcome.topic,
                "created_at": self._clock.now(),
            }
        )

    def dead_end_questions(self) -> list[str]:
        return [e["question"] for e in self._entries if e["outcome"] == "dead_end"]

    def volume_stats(self) -> VolumeStats:
        per_day: dict[str, int] = {}
        topics: dict[str, int] = {}
        answered = dead_end = 0
        for entry in self._entries:
            day = entry["created_at"].date().isoformat()
            per_day[day] = per_day.get(day, 0) + 1
            if entry["topic"]:
                topics[entry["topic"]] = topics.get(entry["topic"], 0) + 1
            if entry["outcome"] == "dead_end":
                dead_end += 1
            else:
                answered += 1
        busiest = sorted(topics.items(), key=lambda kv: (-kv[1], kv[0]))
        return VolumeStats(
            questions_per_day=per_day,
            busiest_topics=busiest,
            lead_count=0,
            answered_count=answered,
            dead_end_count=dead_end,
        )

    def purge_before(self, cutoff: dt.date) -> int:
        before = len(self._entries)
        self._entries = [e for e in self._entries if e["created_at"].date() >= cutoff]
        return before - len(self._entries)


class InMemoryContentRepository:
    def __init__(self) -> None:
        self._docs: dict[str, Document] = {}

    def get(self, doc_id: str) -> Document | None:
        return self._docs.get(doc_id)

    def save_draft(self, doc_id, *, topic, title, body, metadata) -> Document:
        existing = self._docs.get(doc_id)
        doc = Document(
            id=doc_id,
            topic=topic,
            title=title,
            draft_body=body,
            published_body=existing.published_body if existing else None,
            published_version=existing.published_version if existing else 0,
            last_updated=existing.last_updated if existing else None,
            metadata=dict(metadata),
        )
        self._docs[doc_id] = doc
        return doc

    def mark_published(self, doc_id, *, version, body, published_at) -> Document:
        doc = replace(
            self._docs[doc_id],
            published_body=body,
            published_version=version,
            last_updated=published_at,
        )
        self._docs[doc_id] = doc
        return doc


class InMemoryChunkStore:
    """Doubles as ChunkWriter (publish target) and Retriever (keyword search), so
    publishing content makes it answerable in the demo without an embedding server."""

    def __init__(self) -> None:
        self._by_doc: dict[str, list[RetrievedChunk]] = {}

    def seed(self, chunks: list[RetrievedChunk]) -> None:
        for chunk in chunks:
            self._by_doc.setdefault(chunk.document_id, []).append(chunk)

    def replace_document_chunks(self, document_id: str, chunks: list[ChunkToWrite]) -> None:
        self._by_doc[document_id] = [
            RetrievedChunk(
                chunk_id=f"{document_id}-{i}",
                document_id=document_id,
                text=c.text,
                topic=c.topic,
                score=0.0,
                metadata=dict(c.metadata),
            )
            for i, c in enumerate(chunks)
        ]

    def retrieve(self, query: str, *, top_k: int = 5) -> list[RetrievedChunk]:
        # Lightweight TF-IDF: a chunk's score is the fraction of the query's *term
        # importance* it covers, where importance = IDF (rare terms dominate). Query
        # terms absent from the corpus carry no weight, so verbose phrasing and
        # non-matching words ("tell me about…") don't sink a strong specific match.
        wanted = _keywords(query)
        if not wanted:
            return []
        indexed = [
            (chunk, _keywords(chunk.text))
            for chunks in self._by_doc.values()
            for chunk in chunks
        ]
        n = len(indexed)
        if n == 0:
            return []

        doc_freq: dict[str, int] = {}
        for _, terms in indexed:
            for term in terms & wanted:
                doc_freq[term] = doc_freq.get(term, 0) + 1

        def idf(term: str) -> float:
            df = doc_freq.get(term, 0)
            return math.log((1 + n) / (1 + df)) + 1 if df else 0.0

        importance = sum(idf(term) for term in wanted)
        if importance == 0:  # no query term appears in the corpus
            return []

        scored = []
        for chunk, terms in indexed:
            matched = wanted & terms
            if matched:
                score = sum(idf(term) for term in matched) / importance
                scored.append(replace(chunk, score=score))
        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[:top_k]
