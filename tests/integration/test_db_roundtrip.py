"""Opt-in real-Postgres roundtrip.

Runs only when psycopg is installed AND ``TEST_DATABASE_URL`` is set — e.g. in CI
after ``make up && make migrate``. Skipped in environments without a database
(the adapter logic itself is covered deterministically elsewhere).
"""

import datetime as dt
import os

import pytest

psycopg = pytest.importorskip("psycopg")

from takshashila_chatbot.adapters.connection_executor import ConnectionExecutor
from takshashila_chatbot.adapters.pg_lead_repository import PgLeadRepository
from takshashila_chatbot.application.lead_service import LeadDraft

_DSN = os.environ.get("TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _DSN, reason="set TEST_DATABASE_URL to run real-Postgres tests"),
]


def test_lead_save_and_list_roundtrip():
    conn = psycopg.connect(_DSN)
    conn.autocommit = True
    try:
        repo = PgLeadRepository(ConnectionExecutor(conn))
        draft = LeadDraft(
            name="RoundtripTest",
            email="rt@example.com",
            phone=None,
            program=None,
            message=None,
            dead_end_question=None,
            created_at=dt.datetime.now(dt.timezone.utc),
        )
        stored = repo.save(draft)
        assert stored.id
        assert stored.id in [lead.id for lead in repo.list()]
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM leads WHERE name = %s", ("RoundtripTest",))
        conn.close()
