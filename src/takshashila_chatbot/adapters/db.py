"""Database access seam.

Adapters depend on this minimal ``Executor`` rather than a concrete driver, so
their SQL and row-mapping are unit-testable with a fake. Production wiring supplies
a psycopg-backed executor, e.g.::

    class PsycopgExecutor:
        def __init__(self, conn): self._conn = conn
        def execute(self, sql, params=()):
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall() if cur.description else []
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol


class Executor(Protocol):
    def execute(self, sql: str, params: Sequence[Any] = ()) -> list[tuple]: ...
