"""pgvector retriever — embeds the query and runs a cosine-similarity search over
published KB chunks. Implements the ``Retriever`` port.

The retriever returns the top-k scored chunks; the grounding gate in
``AnswerService`` decides whether any clear the threshold (so retrieval policy and
grounding policy stay separate).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..application.ports import Embedder
from ..domain.retrieval import RetrievedChunk
from .db import Executor

SEARCH_SQL = """
SELECT chunk_id, document_id, chunk_text, topic, metadata,
       1 - (embedding <=> %s::vector) AS score
FROM kb_chunks
WHERE published = TRUE
ORDER BY embedding <=> %s::vector
LIMIT %s
"""


def to_vector_literal(embedding: Sequence[float]) -> str:
    """Render an embedding as a pgvector literal, e.g. ``[0.1,0.2,0.3]``."""
    return "[" + ",".join(str(value) for value in embedding) + "]"


def row_to_chunk(row: Sequence) -> RetrievedChunk:
    chunk_id, document_id, text, topic, metadata, score = row
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        text=text,
        topic=topic,
        score=float(score),
        metadata=metadata if isinstance(metadata, Mapping) else {},
    )


class PgVectorRetriever:
    def __init__(self, embedder: Embedder, executor: Executor) -> None:
        self._embedder = embedder
        self._executor = executor

    def retrieve(self, query: str, *, top_k: int = 5) -> list[RetrievedChunk]:
        vector = to_vector_literal(self._embedder.embed(query))
        rows = self._executor.execute(SEARCH_SQL, (vector, vector, top_k))
        return [row_to_chunk(row) for row in rows]
