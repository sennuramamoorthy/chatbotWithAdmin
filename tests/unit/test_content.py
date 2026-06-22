"""Content chunking core (US-8 publish → re-index)."""

import pytest

from takshashila_chatbot.domain.content import chunk_text

pytestmark = pytest.mark.unit


def test_single_paragraph_is_one_chunk():
    assert chunk_text("The B.Tech CSE fee is INR 1,50,000 per year.") == [
        "The B.Tech CSE fee is INR 1,50,000 per year."
    ]


def test_blank_line_separated_paragraphs_split():
    assert chunk_text("Fees are due in June.\n\nHostel is extra.") == [
        "Fees are due in June.",
        "Hostel is extra.",
    ]


def test_whitespace_only_yields_no_chunks():
    assert chunk_text("   \n\n  \t ") == []


def test_long_paragraph_is_hard_split():
    body = "x" * 1100
    chunks = chunk_text(body, max_chars=500)
    assert [len(c) for c in chunks] == [500, 500, 100]


def test_paragraphs_are_trimmed():
    assert chunk_text("  spaced out  ") == ["spaced out"]
