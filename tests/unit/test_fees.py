"""Fee due-date status — upcoming / due today / overdue (US-2, AC-2.4)."""

import datetime as dt

import pytest

from takshashila_chatbot.domain.fees import FeeState, fee_status

pytestmark = pytest.mark.unit

DUE = dt.date(2026, 6, 30)


def test_upcoming_when_due_in_future():  # TC-008 / AC-2.4
    status = fee_status(DUE, dt.date(2026, 6, 1))
    assert status.state is FeeState.UPCOMING
    assert status.days_until_due == 29


def test_due_today_on_due_date():  # AC-2.4
    status = fee_status(DUE, DUE)
    assert status.state is FeeState.DUE_TODAY
    assert status.days_until_due == 0


def test_overdue_when_due_passed():  # TC-007 / EC-5
    status = fee_status(DUE, dt.date(2026, 7, 5))
    assert status.state is FeeState.OVERDUE
    assert status.days_until_due == -5
