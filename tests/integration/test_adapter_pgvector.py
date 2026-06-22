"""PgVectorRetriever — embed query, run a similarity search, map rows.

The pure pieces (vector literal, row mapping) and the orchestration are tested
deterministically with a recording executor; the literal cursor call is the only
thing that needs a real Postgres (covered by an opt-in DB integration test later).
"""

import pytest

from takshashila_chatbot.adapters.pgvector_retriever import (
    PgVectorRetriever,
    row_to_chunk,
    to_vector_literal,
)
from takshashila_chatbot.domain.retrieval import RetrievedChunk
from takshashila_chatbot.testing.fakes import FakeEmbedder, RecordingExecutor

pytestmark = pytest.mark.integration


def test_to_vector_literal():
    assert to_vector_literal([0.1, 0.2, 0.3]) == "[0.1,0.2,0.3]"


def test_row_to_chunk_maps_fields_and_metadata():
    row = ("c1", "d1", "text", "fees", {"due_date": "2026-06-30"}, 0.87)
    assert row_to_chunk(row) == RetrievedChunk(
        "c1", "d1", "text", "fees", 0.87, {"due_date": "2026-06-30"}
    )


def test_row_to_chunk_handles_null_metadata():
    assert row_to_chunk(("c1", "d1", "text", "courses", None, 0.5)).metadata == {}


def test_retrieve_embeds_query_runs_search_and_maps_rows():
    embedder = FakeEmbedder([0.1, 0.2, 0.3])
    executor = RecordingExecutor(
        results=[[("c1", "fees-doc", "Fee is X", "fees", {"due_date": "2026-12-31"}, 0.9)]]
    )
    retriever = PgVectorRetriever(embedder, executor)

    chunks = retriever.retrieve("what is the fee?", top_k=3)

    assert embedder.seen == ["what is the fee?"]
    assert len(chunks) == 1
    assert chunks[0].document_id == "fees-doc"
    assert chunks[0].score == 0.9

    sql, params = executor.calls[0]
    assert "kb_chunks" in sql
    assert "[0.1,0.2,0.3]" in params  # the embedded query vector
    assert 3 in params  # top_k
