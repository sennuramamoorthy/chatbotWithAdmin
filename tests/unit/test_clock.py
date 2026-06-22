"""Clock abstraction — the enabler that makes every date/time test deterministic."""

import datetime as dt

import pytest

from takshashila_chatbot.domain.clock import IST, FixedClock, SystemClock

pytestmark = pytest.mark.unit


def test_fixed_clock_returns_configured_today():
    clock = FixedClock(dt.datetime(2026, 6, 15, 10, 0, tzinfo=IST))
    assert clock.today() == dt.date(2026, 6, 15)


def test_fixed_clock_converts_to_business_timezone():
    # 23:00 UTC on Jun 14 == 04:30 IST on Jun 15 -> business date is the 15th.
    utc_instant = dt.datetime(2026, 6, 14, 23, 0, tzinfo=dt.timezone.utc)
    clock = FixedClock(utc_instant)
    assert clock.today() == dt.date(2026, 6, 15)


def test_fixed_clock_naive_datetime_assumed_ist():
    clock = FixedClock(dt.datetime(2026, 6, 15, 0, 30))
    assert clock.today() == dt.date(2026, 6, 15)


def test_fixed_clock_advance_crosses_midnight():
    clock = FixedClock(dt.datetime(2026, 6, 15, 23, 59, 30, tzinfo=IST))
    clock.advance(60)  # +60s crosses midnight IST
    assert clock.today() == dt.date(2026, 6, 16)


def test_system_clock_is_timezone_aware():
    clock = SystemClock()
    assert clock.now().tzinfo is not None
    assert isinstance(clock.today(), dt.date)
