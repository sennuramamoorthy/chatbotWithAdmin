"""Executor backed by any DB-API 2.0 connection (psycopg3 included).

Driver-agnostic by design: it never imports a specific driver, so its cursor
handling is unit-testable with a fake connection. Production passes a real
``psycopg.connect(...)`` connection.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol


class _Connection(Protocol):
    def cursor(self) -> Any: ...


class ConnectionExecutor:
    def __init__(self, connection: _Connection) -> None:
        self._connection = connection

    def execute(self, sql: str, params: Sequence[Any] = ()) -> list[tuple]:
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            if cursor.description is not None:  # a result set is available
                return cursor.fetchall()
            return []
