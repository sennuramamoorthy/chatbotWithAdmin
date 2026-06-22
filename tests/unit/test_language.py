"""Script-based language detection (FR-7, fast deterministic pre-signal).

This detects Tamil *script* vs Latin; semantic/romanized-Tamil detection
("fees enna?") is the LLM's job, validated at the eval layer.
"""

import pytest

from takshashila_chatbot.domain.language import Language, detect_language

pytestmark = pytest.mark.unit


def test_english_detected():
    assert detect_language("What is the B.Tech CSE fee?") is Language.EN


def test_tamil_script_detected():  # "How much is the fee?" in Tamil
    assert detect_language("கட்டணம் எவ்வளவு?") is Language.TA


def test_mixed_script_detected():
    assert detect_language("CSE fees கட்டணம்?") is Language.MIXED


@pytest.mark.parametrize("text", ["12345 ?!", "   ", ""])
def test_no_letters_is_unknown(text):
    assert detect_language(text) is Language.UNKNOWN
