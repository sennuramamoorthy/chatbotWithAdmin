"""Deterministic fakes implementing the application ports."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Callable, Sequence
from typing import Any

from ..application.ports import GenerationRequest, QuestionOutcome
from ..domain.retrieval import RetrievedChunk

Router = Callable[[str, tuple], "tuple[list[tuple], object | None]"]


class FakeRetriever:
    """Returns a fixed, pre-scripted set of chunks (top_k applied)."""

    def __init__(self, chunks: Sequence[RetrievedChunk]) -> None:
        self._chunks = list(chunks)

    def retrieve(self, query: str, *, top_k: int = 5) -> list[RetrievedChunk]:
        return self._chunks[:top_k]


class FakeLanguageModel:
    """Records requests and echoes the facts + context, so grounded information
    surfaces in the answer for property assertions (never asserts exact strings)."""

    def __init__(self) -> None:
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> str:
        self.requests.append(request)
        return " ".join([*request.facts, request.context]).strip()

    def stream_tokens(self, request: GenerationRequest):
        # Lets the same fake satisfy StreamingLanguageModel (word-by-word echo).
        self.requests.append(request)
        text = " ".join([*request.facts, request.context]).strip()
        for word in text.split(" "):
            yield word + " "

    @property
    def call_count(self) -> int:
        return len(self.requests)


class RecordingOutcomeSink:
    """Captures logged outcomes for assertions about the learning-loop signal."""

    def __init__(self) -> None:
        self.records: list[QuestionOutcome] = []

    def record(self, outcome: QuestionOutcome) -> None:
        self.records.append(outcome)


class FakeEmbedder:
    """Returns a fixed vector regardless of input."""

    def __init__(self, vector: Sequence[float] = (0.1, 0.2, 0.3)) -> None:
        self._vector = list(vector)
        self.seen: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.seen.append(text)
        return list(self._vector)


_EMBED_STOPWORDS = frozenset(
    {"the", "is", "a", "an", "what", "of", "in", "to", "for", "and", "at", "on",
     "my", "i", "are", "when", "where", "how", "do", "does", "you", "please",
     "today", "me", "about", "tell", "there", "with", "can"}
)


class HashingEmbedder:
    """Deterministic bag-of-words hashing embedder for the **demo only**.

    Distinct questions get distinct vectors (so the learning-loop clusters rank
    meaningfully on the dashboard) while near-duplicate phrasings stay close under
    cosine similarity. Stable across processes (hashlib, not salted ``hash``). Not
    for production — real semantics come from the self-hosted model via HttpEmbedder.
    """

    def __init__(self, dim: int = 96) -> None:
        self._dim = dim
        self.seen: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.seen.append(text)
        vector = [0.0] * self._dim
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            if token in _EMBED_STOPWORDS:
                continue
            bucket = int.from_bytes(hashlib.md5(token.encode()).digest()[:4], "big")
            vector[bucket % self._dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vector))
        return [v / norm for v in vector] if norm else vector


class ScriptedEmbedder:
    """Maps known texts to fixed vectors (for deterministic clustering tests)."""

    def __init__(
        self,
        vectors: dict[str, Sequence[float]],
        default: Sequence[float] = (0.0,),
    ) -> None:
        self._vectors = {k: list(v) for k, v in vectors.items()}
        self._default = list(default)
        self.seen: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.seen.append(text)
        return list(self._vectors.get(text, self._default))


class RecordingExecutor:
    """A fake SQL executor: records (sql, params) calls and returns queued rows."""

    def __init__(self, results: Sequence[Sequence[tuple]] | None = None) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self._results: list[Sequence[tuple]] = [list(r) for r in (results or [])]

    def execute(self, sql: str, params: Sequence[Any] = ()) -> list[tuple]:
        self.calls.append((sql, tuple(params)))
        return list(self._results.pop(0)) if self._results else []


class FakeCursor:
    """DB-API 2.0-ish cursor; rows + description decided by a router on execute."""

    def __init__(self, router: Router) -> None:
        self._router = router
        self.description: object | None = None
        self._rows: list[tuple] = []
        self.calls: list[tuple[str, tuple]] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        self.calls.append((sql, tuple(params)))
        self._rows, self.description = self._router(sql, tuple(params))

    def fetchall(self) -> list[tuple]:
        return list(self._rows)


class FakeConnection:
    """DB-API 2.0-ish connection driven by a ``router(sql, params) -> (rows, description)``."""

    def __init__(self, router: Router) -> None:
        self._router = router
        self.cursors: list[FakeCursor] = []

    def cursor(self) -> FakeCursor:
        cursor = FakeCursor(self._router)
        self.cursors.append(cursor)
        return cursor
