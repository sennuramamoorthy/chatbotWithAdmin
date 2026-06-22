"""Postgres question log — identity-free (FR-18, NFR-6).

One cohesive adapter implementing OutcomeSink (record), DeadEndLogStore
(dead-end texts for clustering), StatsStore (volume basics), and Purger (12-month
retention). No visitor identity is stored.
"""

from __future__ import annotations

import datetime as dt

from ..application.ports import QuestionOutcome, VolumeStats
from ..domain.clock import Clock
from .db import Executor

_RECORD_SQL = """
INSERT INTO question_logs (question_text, outcome, topic, detected_lang, created_at)
VALUES (%s, %s, %s, %s, %s)
"""
_DEAD_ENDS_SQL = "SELECT question_text FROM question_logs WHERE outcome = 'dead_end'"
_PER_DAY_SQL = """
SELECT to_char(created_at, 'YYYY-MM-DD') AS day, count(*)
FROM question_logs GROUP BY day ORDER BY day
"""
_TOPICS_SQL = """
SELECT topic, count(*) AS c FROM question_logs
WHERE topic IS NOT NULL GROUP BY topic ORDER BY c DESC, topic
"""
_OUTCOMES_SQL = "SELECT outcome, count(*) FROM question_logs GROUP BY outcome"
_PURGE_SQL = "DELETE FROM question_logs WHERE created_at < %s RETURNING id"


class PgQuestionLog:
    def __init__(self, executor: Executor, clock: Clock) -> None:
        self._executor = executor
        self._clock = clock

    def record(self, outcome: QuestionOutcome) -> None:
        self._executor.execute(
            _RECORD_SQL,
            (outcome.question, outcome.outcome, outcome.topic, outcome.language, self._clock.now()),
        )

    def dead_end_questions(self) -> list[str]:
        return [row[0] for row in self._executor.execute(_DEAD_ENDS_SQL)]

    def volume_stats(self) -> VolumeStats:
        per_day = {row[0]: row[1] for row in self._executor.execute(_PER_DAY_SQL)}
        busiest = [(row[0], row[1]) for row in self._executor.execute(_TOPICS_SQL)]
        by_outcome = {row[0]: row[1] for row in self._executor.execute(_OUTCOMES_SQL)}
        return VolumeStats(
            questions_per_day=per_day,
            busiest_topics=busiest,
            lead_count=0,
            answered_count=by_outcome.get("answered", 0),
            dead_end_count=by_outcome.get("dead_end", 0),
        )

    def purge_before(self, cutoff: dt.date) -> int:
        return len(self._executor.execute(_PURGE_SQL, (cutoff,)))
