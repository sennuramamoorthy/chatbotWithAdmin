"""Date-fact enrichment (FR-4, FR-5).

Turns retrieved fee/admission chunks carrying structured dates into computed
status facts using the real deterministic date functions. These facts are handed
to the LLM as ground truth so it never compares dates itself.
"""

import datetime as dt

import pytest

from takshashila_chatbot.domain.enrichment import compute_facts
from takshashila_chatbot.domain.retrieval import RetrievedChunk

pytestmark = pytest.mark.unit


def _chunk(topic: str, metadata: dict[str, str]) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="c1", document_id="d1", text="text", topic=topic, score=0.9, metadata=metadata
    )


def test_overdue_fee_fact():  # TC-007 path, through enrichment
    facts = compute_facts([_chunk("fees", {"due_date": "2026-06-30"})], dt.date(2026, 7, 5))
    assert any("overdue" in f.lower() for f in facts)


def test_upcoming_fee_fact():
    facts = compute_facts([_chunk("fees", {"due_date": "2026-12-31"})], dt.date(2026, 6, 1))
    assert any("upcoming" in f.lower() for f in facts)


def test_admission_closed_fact():  # TC-005 path, through enrichment
    chunk = _chunk("admissions", {"open_date": "2026-01-01", "close_date": "2026-06-30"})
    facts = compute_facts([chunk], dt.date(2026, 7, 1))
    assert any("closed" in f.lower() for f in facts)


def test_admission_open_on_close_date_is_inclusive():  # TC-006 path
    chunk = _chunk("admissions", {"open_date": "2026-01-01", "close_date": "2026-06-30"})
    facts = compute_facts([chunk], dt.date(2026, 6, 30))
    assert any("open" in f.lower() for f in facts)


def test_no_facts_without_date_metadata():
    assert compute_facts([_chunk("fees", {})], dt.date(2026, 6, 1)) == []


def test_no_facts_for_non_date_topic():
    chunk = _chunk("placements", {"due_date": "2026-06-30"})
    assert compute_facts([chunk], dt.date(2026, 6, 1)) == []
