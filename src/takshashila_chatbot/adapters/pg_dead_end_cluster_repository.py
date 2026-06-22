"""Postgres dead-end cluster store — frequency-ranked knowledge gaps (AC-9.1)."""

from __future__ import annotations

from ..application.ports import DeadEndGroup
from .db import Executor

_DELETE_ALL_SQL = "DELETE FROM dead_end_clusters"
_INSERT_SQL = "INSERT INTO dead_end_clusters (representative_text, frequency) VALUES (%s, %s)"
_RANKED_SQL = """
SELECT representative_text, frequency FROM dead_end_clusters
ORDER BY frequency DESC LIMIT %s
"""


class PgDeadEndClusterRepository:
    def __init__(self, executor: Executor) -> None:
        self._executor = executor

    def replace_all(self, groups: list[DeadEndGroup]) -> None:
        self._executor.execute(_DELETE_ALL_SQL)
        for group in groups:
            self._executor.execute(_INSERT_SQL, (group.representative_text, group.frequency))

    def ranked(self, limit: int = 50) -> list[DeadEndGroup]:
        rows = self._executor.execute(_RANKED_SQL, (limit,))
        return [DeadEndGroup(representative_text=row[0], frequency=row[1]) for row in rows]
