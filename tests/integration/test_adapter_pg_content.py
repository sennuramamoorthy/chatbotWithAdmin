"""PgContentRepository + PgChunkWriter — content persistence + re-index writes."""

import datetime as dt

import pytest

from takshashila_chatbot.adapters.pg_chunk_writer import PgChunkWriter
from takshashila_chatbot.adapters.pg_content_repository import PgContentRepository
from takshashila_chatbot.application.content_service import ChunkToWrite
from takshashila_chatbot.testing.fakes import RecordingExecutor

pytestmark = pytest.mark.integration

_ROW = (
    "hostel", "fees", "Hostel", "draft body", "pub body", 2,
    dt.datetime(2026, 6, 16, 12, 0), {"due_date": "2026-12-31"},
)


def test_get_returns_none_when_absent():
    assert PgContentRepository(RecordingExecutor()).get("x") is None


def test_get_maps_row():
    doc = PgContentRepository(RecordingExecutor(results=[[_ROW]])).get("hostel")
    assert doc.id == "hostel"
    assert doc.published_version == 2
    assert doc.metadata == {"due_date": "2026-12-31"}


def test_get_handles_json_string_metadata():
    row = (*_ROW[:7], '{"a": "b"}')  # jsonb returned as text
    doc = PgContentRepository(RecordingExecutor(results=[[row]])).get("hostel")
    assert doc.metadata == {"a": "b"}


def test_save_draft_upserts_and_maps():
    executor = RecordingExecutor(results=[[_ROW]])
    doc = PgContentRepository(executor).save_draft(
        "hostel", topic="fees", title="Hostel", body="b", metadata={"x": "y"}
    )
    sql, params = executor.calls[0]
    assert "insert into kb_documents" in sql.lower()
    assert "on conflict" in sql.lower()
    assert "hostel" in params
    assert doc.id == "hostel"


def test_mark_published_updates_and_snapshots_version():
    executor = RecordingExecutor(results=[[_ROW], []])
    doc = PgContentRepository(executor).mark_published(
        "hostel", version=2, body="b", published_at=dt.datetime(2026, 6, 16, 12, 0)
    )
    assert "update kb_documents" in executor.calls[0][0].lower()
    assert "insert into kb_document_versions" in executor.calls[1][0].lower()
    assert doc.published_version == 2


def test_chunk_writer_deletes_then_inserts_with_embedding():
    executor = RecordingExecutor()
    PgChunkWriter(executor).replace_document_chunks(
        "hostel", [ChunkToWrite("Fee is 60k", [0.1, 0.2], "fees", {"k": "v"})]
    )
    assert "delete from kb_chunks" in executor.calls[0][0].lower()
    assert executor.calls[0][1] == ("hostel",)

    insert_sql, params = executor.calls[1]
    assert "insert into kb_chunks" in insert_sql.lower()
    assert "hostel-0" in params
    assert "[0.1,0.2]" in params  # pgvector literal
    assert "Fee is 60k" in params
