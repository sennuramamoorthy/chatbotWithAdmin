"""In-memory repositories — purge and stats edge cases (FR-18, AC-9.2/9.3)."""

import datetime as dt

import pytest

from takshashila_chatbot.application.lead_service import LeadDraft
from takshashila_chatbot.application.ports import QuestionOutcome
from takshashila_chatbot.application.repositories import (
    InMemoryChunkStore,
    InMemoryLeadRepository,
    InMemoryQuestionLog,
)
from takshashila_chatbot.domain.clock import IST, FixedClock
from takshashila_chatbot.domain.retrieval import RetrievedChunk

pytestmark = pytest.mark.integration


def _draft(created_at: dt.datetime) -> LeadDraft:
    return LeadDraft("Asha", "a@b.co", None, None, None, None, created_at)


def test_lead_purge_before_removes_only_old_leads():
    repo = InMemoryLeadRepository()
    repo.save(_draft(dt.datetime(2024, 1, 1, tzinfo=IST)))  # older than cutoff
    repo.save(_draft(dt.datetime(2026, 6, 16, tzinfo=IST)))  # kept

    removed = repo.purge_before(dt.date(2025, 6, 16))

    assert removed == 1
    assert len(repo.list()) == 1


def test_question_log_purge_and_stats_skip_null_topic():
    clock = FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))
    log = InMemoryQuestionLog(clock)
    log.record(QuestionOutcome("q1", "answered", None, "en"))  # no topic

    assert log.volume_stats().busiest_topics == []  # null topic not counted

    removed = log.purge_before(dt.date(2027, 1, 1))  # cutoff after the entry
    assert removed == 1
    assert log.volume_stats().questions_per_day == {}


def test_question_log_counts_answered_and_dead_end_outcomes():
    clock = FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))
    log = InMemoryQuestionLog(clock)
    log.record(QuestionOutcome("q1", "answered", "fees", "en"))
    log.record(QuestionOutcome("q2", "answered", "fees", "en"))
    log.record(QuestionOutcome("q3", "dead_end", "facilities", "en"))

    stats = log.volume_stats()
    assert stats.answered_count == 2  # feeds the answer-coverage KPI
    assert stats.dead_end_count == 1


def test_chunk_store_ranks_by_tfidf_relevance():
    store = InMemoryChunkStore()
    store.seed([
        RetrievedChunk("h", "hostels", "Hostel Mailam annual hostel fee 75000.", "facilities", 0.0, {}),
        RetrievedChunk("b", "btech", "B.Tech CSE course fee 150000.", "courses", 0.0, {}),
    ])
    hits = store.retrieve("hostel fee")
    assert hits[0].document_id == "hostels"  # rare "hostel" outweighs the shared "fee"
    assert hits[1].score < hits[0].score  # B.Tech matched only the common term
    assert store.retrieve("weather forecast") == []  # no query term in the corpus
    assert store.retrieve("what is the") == []  # all stopwords -> nothing to match


def test_chunk_store_matches_plurals_via_stemming():
    store = InMemoryChunkStore()
    store.seed([RetrievedChunk("h", "hostels", "Hostel Mailam annual fee 75000.", "facilities", 0.0, {})])
    hits = store.retrieve("hostels")  # 'hostels' stems to 'hostel' -> matches "Hostel"
    assert hits and hits[0].document_id == "hostels"
