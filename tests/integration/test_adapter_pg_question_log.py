"""PgQuestionLog — identity-free log: record, dead-ends, stats, purge."""

import datetime as dt

import pytest

from takshashila_chatbot.adapters.pg_question_log import PgQuestionLog
from takshashila_chatbot.application.ports import QuestionOutcome
from takshashila_chatbot.domain.clock import IST, FixedClock
from takshashila_chatbot.testing.fakes import RecordingExecutor

pytestmark = pytest.mark.integration


def _clock() -> FixedClock:
    return FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))


def test_record_inserts_log():
    executor = RecordingExecutor()
    PgQuestionLog(executor, _clock()).record(QuestionOutcome("hi", "dead_end", "fees", "en"))
    sql, params = executor.calls[0]
    assert "insert into question_logs" in sql.lower()
    assert "hi" in params and "dead_end" in params and "fees" in params


def test_dead_end_questions_returns_texts():
    executor = RecordingExecutor(results=[[("q1",), ("q2",)]])
    assert PgQuestionLog(executor, _clock()).dead_end_questions() == ["q1", "q2"]


def test_volume_stats_aggregates_per_day_topics_and_outcomes():
    executor = RecordingExecutor(
        results=[
            [("2026-06-16", 3)],
            [("fees", 2), ("facilities", 1)],
            [("answered", 2), ("dead_end", 1)],
        ]
    )
    stats = PgQuestionLog(executor, _clock()).volume_stats()
    assert stats.questions_per_day == {"2026-06-16": 3}
    assert stats.busiest_topics == [("fees", 2), ("facilities", 1)]
    assert stats.answered_count == 2
    assert stats.dead_end_count == 1
    assert stats.lead_count == 0


def test_purge_before_returns_deleted_count():
    executor = RecordingExecutor(results=[[(1,), (2,)]])
    deleted = PgQuestionLog(executor, _clock()).purge_before(dt.date(2025, 6, 16))
    assert deleted == 2
    sql, params = executor.calls[0]
    assert "delete from question_logs" in sql.lower()
    assert dt.date(2025, 6, 16) in params
