"""PgLeadRepository — INSERT ... RETURNING and row mapping via a fake executor."""

import datetime as dt

import pytest

from takshashila_chatbot.adapters.pg_lead_repository import PgLeadRepository
from takshashila_chatbot.application.lead_service import LeadDraft
from takshashila_chatbot.testing.fakes import RecordingExecutor

pytestmark = pytest.mark.integration


def _draft() -> LeadDraft:
    return LeadDraft(
        name="Asha",
        email="asha@example.com",
        phone=None,
        program="B.Tech CSE",
        message="Please call",
        dead_end_question="hostel fee?",
        created_at=dt.datetime(2026, 6, 15, 12, 0),
    )


def test_save_inserts_and_returns_stored_lead_with_id():
    executor = RecordingExecutor(results=[[(42,)]])  # INSERT ... RETURNING id
    repo = PgLeadRepository(executor)

    stored = repo.save(_draft())

    assert stored.id == "42"
    assert stored.name == "Asha"
    assert stored.delivery_status == "pending"

    sql, params = executor.calls[0]
    assert "insert into leads" in sql.lower()
    assert "Asha" in params
    assert "pending" in params


def test_list_maps_rows_to_stored_leads():
    row = (
        "7", "Asha", "asha@example.com", None, "B.Tech CSE", "msg", "hostel fee?",
        dt.datetime(2026, 6, 15, 12, 0), "sent",
    )
    repo = PgLeadRepository(RecordingExecutor(results=[[row]]))

    leads = repo.list()

    assert len(leads) == 1
    assert leads[0].id == "7"
    assert leads[0].delivery_status == "sent"


def test_purge_before_deletes_old_leads():
    executor = RecordingExecutor(results=[[(1,)]])
    deleted = PgLeadRepository(executor).purge_before(dt.date(2025, 6, 16))
    assert deleted == 1
    assert "delete from leads" in executor.calls[0][0].lower()
    assert dt.date(2025, 6, 16) in executor.calls[0][1]
