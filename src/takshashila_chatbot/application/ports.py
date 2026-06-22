"""Ports — the abstract boundaries between the pipeline and external systems.

Concrete adapters (self-hosted LLM, embeddings+vector retriever, Postgres outcome
log) implement these at the edges; tests inject fakes. Keeping these as Protocols
lets the deterministic core stay testable with zero I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..domain.retrieval import RetrievedChunk


@dataclass(frozen=True)
class GenerationRequest:
    """Everything the model needs to phrase a grounded answer."""

    question: str
    language: str
    context: str
    facts: tuple[str, ...] = ()


@dataclass(frozen=True)
class QuestionOutcome:
    """A logged turn — no visitor identity (FR-18). Feeds the learning loop."""

    question: str
    outcome: str  # "answered" | "dead_end"
    topic: str | None
    language: str


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class Retriever(Protocol):
    def retrieve(self, query: str, *, top_k: int = 5) -> list[RetrievedChunk]: ...


class LanguageModel(Protocol):
    def generate(self, request: GenerationRequest) -> str: ...


class OutcomeSink(Protocol):
    def record(self, outcome: QuestionOutcome) -> None: ...


# --- Learning loop (US-9, FR-17/18) ----------------------------------------


@dataclass(frozen=True)
class DeadEndGroup:
    """A cluster of similar unanswered questions, ranked by frequency (AC-9.1)."""

    representative_text: str
    frequency: int


@dataclass(frozen=True)
class VolumeStats:
    questions_per_day: dict[str, int]
    busiest_topics: list[tuple[str, int]]
    lead_count: int
    # Outcome breakdown feeds the answer-coverage KPI (answered / total). Defaulted
    # so existing constructions and DashboardService's ``replace`` stay valid.
    answered_count: int = 0
    dead_end_count: int = 0


class DeadEndLogStore(Protocol):
    def dead_end_questions(self) -> list[str]: ...


class DeadEndClusterRepository(Protocol):
    def replace_all(self, groups: list[DeadEndGroup]) -> None: ...

    def ranked(self, limit: int = 50) -> list[DeadEndGroup]: ...


class StatsStore(Protocol):
    def volume_stats(self) -> VolumeStats: ...


class Purger(Protocol):
    def purge_before(self, cutoff) -> int: ...
