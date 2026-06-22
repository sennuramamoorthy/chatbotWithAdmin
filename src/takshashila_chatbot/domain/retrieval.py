"""Retrieved-chunk value object and the grounding gate (FR-1, AC-1.2, NFR-5).

``RetrievedChunk`` is a domain value object (a piece of grounded knowledge with a
similarity score). The grounding helpers decide whether retrieval cleared the bar
to answer at all — if not, the pipeline falls back instead of asking the LLM to
guess.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

# Below this similarity, retrieval is treated as "no grounded content".
DEFAULT_GROUNDING_THRESHOLD = 0.6


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    document_id: str
    text: str
    topic: str
    score: float
    # May carry structured dates for date-aware topics, e.g.
    # {"due_date": "2026-06-30"} or {"open_date": ..., "close_date": ...}.
    metadata: Mapping[str, str] = field(default_factory=dict)


def select_grounded(
    chunks: Sequence[RetrievedChunk],
    threshold: float = DEFAULT_GROUNDING_THRESHOLD,
) -> list[RetrievedChunk]:
    """Return the chunks at or above ``threshold``, preserving order."""
    return [c for c in chunks if c.score >= threshold]


def is_grounded(
    chunks: Sequence[RetrievedChunk],
    threshold: float = DEFAULT_GROUNDING_THRESHOLD,
) -> bool:
    """True iff at least one chunk clears the grounding threshold."""
    return len(select_grounded(chunks, threshold)) > 0
