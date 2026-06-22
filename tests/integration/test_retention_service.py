"""RetentionService — purges question logs and leads older than the 12-month cutoff."""

import datetime as dt

import pytest

from takshashila_chatbot.application.retention import RetentionService
from takshashila_chatbot.domain.clock import IST, FixedClock

pytestmark = pytest.mark.integration


class _FakePurger:
    def __init__(self, deleted: int) -> None:
        self._deleted = deleted
        self.cutoff = None

    def purge_before(self, cutoff: dt.date) -> int:
        self.cutoff = cutoff
        return self._deleted


def test_purges_logs_and_leads_before_the_cutoff():
    clock = FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))
    questions, leads = _FakePurger(3), _FakePurger(1)

    service = RetentionService(questions, leads, clock)
    result = service.purge()

    assert result == (3, 1)
    assert questions.cutoff == dt.date(2025, 6, 16)
    assert leads.cutoff == dt.date(2025, 6, 16)
