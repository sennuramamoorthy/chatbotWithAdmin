"""Admission open/closed status — self-computed, inclusive close (US-2)."""

import datetime as dt

import pytest

from takshashila_chatbot.domain.admissions import AdmissionState, admission_status

pytestmark = pytest.mark.unit

OPEN = dt.date(2026, 1, 1)
CLOSE = dt.date(2026, 6, 30)


def test_open_when_today_between_dates():  # TC-004 / AC-2.1
    status = admission_status(OPEN, CLOSE, dt.date(2026, 3, 15))
    assert status.state is AdmissionState.OPEN
    assert status.is_open is True


def test_closed_after_close_date_without_edit():  # TC-005 / AC-2.2 / EC-3
    status = admission_status(OPEN, CLOSE, dt.date(2026, 7, 1))
    assert status.state is AdmissionState.CLOSED
    assert status.is_open is False


def test_open_on_exact_close_date_is_inclusive():  # TC-006 / AC-2.3 / EC-4
    status = admission_status(OPEN, CLOSE, CLOSE)
    assert status.state is AdmissionState.OPEN


def test_open_on_exact_open_date_is_inclusive():
    status = admission_status(OPEN, CLOSE, OPEN)
    assert status.state is AdmissionState.OPEN


def test_upcoming_before_open_date():
    status = admission_status(OPEN, CLOSE, dt.date(2025, 12, 31))
    assert status.state is AdmissionState.UPCOMING
    assert status.is_open is False


def test_invalid_window_raises():
    with pytest.raises(ValueError):
        admission_status(CLOSE, OPEN, OPEN)  # close before open
