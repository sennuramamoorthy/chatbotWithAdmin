"""Cheap input guards run before any LLM call (EC-25, EC-26).

Empty/whitespace input is never sent to the model (saves a call, prompts the
visitor to type); over-cap input asks the visitor to shorten.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

MAX_QUESTION_LEN = 2000


class QuestionVerdict(str, Enum):
    OK = "ok"
    EMPTY = "empty"
    TOO_LONG = "too_long"


@dataclass(frozen=True)
class QuestionCheck:
    verdict: QuestionVerdict
    normalized: str
    message: str | None = None

    @property
    def ok(self) -> bool:
        return self.verdict is QuestionVerdict.OK


def validate_question(
    text: str | None, max_len: int = MAX_QUESTION_LEN
) -> QuestionCheck:
    if text is None or text.strip() == "":
        return QuestionCheck(QuestionVerdict.EMPTY, "", "Please type a question.")

    stripped = text.strip()
    if len(stripped) > max_len:
        return QuestionCheck(
            QuestionVerdict.TOO_LONG,
            stripped,
            "That question is a bit long — please shorten it and try again.",
        )

    return QuestionCheck(QuestionVerdict.OK, stripped)
