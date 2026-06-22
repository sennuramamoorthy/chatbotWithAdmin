"""Grounding gate — the anti-fabrication keystone (FR-1, AC-1.2, NFR-5).

If nothing retrieves above the threshold, the pipeline must NOT call the LLM to
guess; it falls back (TC-002). These are the pure decisions behind that gate.
"""

import pytest

from takshashila_chatbot.domain.retrieval import (
    DEFAULT_GROUNDING_THRESHOLD,
    RetrievedChunk,
    is_grounded,
    select_grounded,
)

pytestmark = pytest.mark.unit


def _chunk(score: float, topic: str = "courses") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"c{score}", document_id="d1", text="text", topic=topic, score=score
    )


def test_grounded_when_a_chunk_meets_threshold():
    assert is_grounded([_chunk(0.9), _chunk(0.3)]) is True


def test_not_grounded_when_all_below_threshold():  # TC-002 / AC-1.2
    assert is_grounded([_chunk(0.2), _chunk(0.1)]) is False


def test_not_grounded_when_empty():
    assert is_grounded([]) is False


def test_threshold_is_inclusive():
    assert is_grounded([_chunk(DEFAULT_GROUNDING_THRESHOLD)]) is True


def test_select_grounded_filters_and_preserves_order():
    a, b, c = _chunk(0.9), _chunk(0.2), _chunk(0.7)
    assert select_grounded([a, b, c]) == [a, c]
