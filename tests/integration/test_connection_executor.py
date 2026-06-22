"""ConnectionExecutor — adapts a DB-API 2.0 connection to the Executor port."""

import pytest

from takshashila_chatbot.adapters.connection_executor import ConnectionExecutor
from takshashila_chatbot.testing.fakes import FakeConnection

pytestmark = pytest.mark.integration


def test_returns_rows_when_statement_has_a_result_set():
    conn = FakeConnection(lambda sql, params: ([(1, "a")], [("id",), ("name",)]))
    executor = ConnectionExecutor(conn)

    rows = executor.execute("SELECT * FROM t WHERE x = %s", ("p",))

    assert rows == [(1, "a")]
    assert conn.cursors[0].calls == [("SELECT * FROM t WHERE x = %s", ("p",))]


def test_returns_empty_when_no_result_set():
    conn = FakeConnection(lambda sql, params: ([], None))  # description is None
    assert ConnectionExecutor(conn).execute("UPDATE t SET x = 1") == []
