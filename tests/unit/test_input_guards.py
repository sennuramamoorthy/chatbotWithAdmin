"""Input guards before any LLM call (EC-25, EC-26). Covers TC-037, TC-039."""

import pytest

from takshashila_chatbot.domain.input_guards import (
    QuestionVerdict,
    validate_question,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("text", ["", "   ", "\n\t  ", None])
def test_empty_or_whitespace_is_rejected(text):  # TC-037 / EC-25
    check = validate_question(text)
    assert check.verdict is QuestionVerdict.EMPTY
    assert check.ok is False  # signals: do not call the LLM


def test_normal_question_is_ok_and_trimmed():
    check = validate_question("  What is the CSE fee?  ")
    assert check.verdict is QuestionVerdict.OK
    assert check.ok is True
    assert check.normalized == "What is the CSE fee?"


def test_over_length_question_is_rejected():  # TC-039 / EC-26
    check = validate_question("x" * 51, max_len=50)
    assert check.verdict is QuestionVerdict.TOO_LONG
    assert check.ok is False


def test_question_at_cap_is_accepted():
    check = validate_question("x" * 50, max_len=50)
    assert check.verdict is QuestionVerdict.OK
