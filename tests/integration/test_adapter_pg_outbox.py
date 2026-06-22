"""PgOutboxStore — INSERT ... RETURNING, retry-eligible SELECT, status updates.

Driver-free: exercised through ``RecordingExecutor`` so we can assert the SQL
keywords, bound params, and row -> OutboxRecord mapping (mirrors EC-18 retry).
"""

import pytest

from takshashila_chatbot.adapters.pg_outbox import OUTBOX_SCHEMA, PgOutboxStore
from takshashila_chatbot.application.lead_delivery import OutboxRecord, OutboxStore
from takshashila_chatbot.testing.fakes import RecordingExecutor

pytestmark = pytest.mark.integration


def test_outbox_schema_creates_table_with_expected_columns():
    ddl = OUTBOX_SCHEMA.lower()
    assert "create table if not exists outbox" in ddl
    assert "id bigserial primary key" in ddl
    assert "recipient text" in ddl
    assert "subject text" in ddl
    assert "body text" in ddl
    assert "status text" in ddl and "default 'pending'" in ddl
    assert "attempts int" in ddl and "default 0" in ddl
    assert "last_error text" in ddl
    assert "created_at timestamptz" in ddl and "default now()" in ddl


def test_store_satisfies_outbox_store_protocol():
    # Structural check that the adapter is a drop-in for the port.
    store: OutboxStore = PgOutboxStore(RecordingExecutor())
    assert hasattr(store, "add")
    assert hasattr(store, "pending")
    assert hasattr(store, "mark_sent")
    assert hasattr(store, "mark_failed")


def test_add_inserts_and_returns_pending_record_with_id():
    executor = RecordingExecutor(results=[[(99,)]])  # INSERT ... RETURNING id
    store = PgOutboxStore(executor)

    record = store.add("asha@example.com", "Your enquiry", "We'll call you")

    assert record == OutboxRecord(
        id="99",
        to="asha@example.com",
        subject="Your enquiry",
        body="We'll call you",
        status="pending",
        attempts=0,
        last_error=None,
    )

    sql, params = executor.calls[0]
    assert "insert into outbox" in sql.lower()
    assert "returning id" in sql.lower()
    assert params == ("asha@example.com", "Your enquiry", "We'll call you")


def test_pending_selects_pending_and_failed_and_maps_rows():
    rows = [
        (1, "a@x.com", "S1", "B1", "pending", 0, None),
        (2, "b@x.com", "S2", "B2", "failed", 3, "smtp down"),
    ]
    executor = RecordingExecutor(results=[rows])
    store = PgOutboxStore(executor)

    pending = store.pending()

    assert pending == [
        OutboxRecord("1", "a@x.com", "S1", "B1", "pending", 0, None),
        OutboxRecord("2", "b@x.com", "S2", "B2", "failed", 3, "smtp down"),
    ]
    sql = executor.calls[0][0].lower()
    assert "select" in sql
    assert "from outbox" in sql
    assert "status in ('pending', 'failed')" in sql


def test_pending_returns_empty_when_no_rows():
    store = PgOutboxStore(RecordingExecutor(results=[[]]))
    assert store.pending() == []


def test_mark_sent_updates_status_to_sent():
    executor = RecordingExecutor()
    PgOutboxStore(executor).mark_sent("42")

    sql, params = executor.calls[0]
    assert "update outbox" in sql.lower()
    assert "status = 'sent'" in sql.lower()
    assert "where id = %s" in sql.lower()
    assert params == ("42",)


def test_mark_failed_increments_attempts_and_records_error():
    executor = RecordingExecutor()
    PgOutboxStore(executor).mark_failed("7", "connection refused")

    sql, params = executor.calls[0]
    lowered = sql.lower()
    assert "update outbox" in lowered
    assert "status = 'failed'" in lowered
    assert "attempts = attempts + 1" in lowered
    assert "last_error = %s" in lowered
    # error bound first, id second (matches "SET last_error = %s WHERE id = %s")
    assert params == ("connection refused", "7")
