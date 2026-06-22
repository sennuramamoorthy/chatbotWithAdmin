"""Content chunking (US-8).

Splits a document body into retrieval chunks: blank-line-separated paragraphs,
with any over-long paragraph hard-split to a max size. Pure and deterministic;
embedding + indexing happen at publish time in the content service.
"""

from __future__ import annotations

DEFAULT_MAX_CHARS = 500


def chunk_text(body: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    chunks: list[str] = []
    for paragraph in body.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= max_chars:
            chunks.append(paragraph)
        else:
            for start in range(0, len(paragraph), max_chars):
                chunks.append(paragraph[start : start + max_chars])
    return chunks
