"""Retention cutoff (FR-18, AC-9.3, TC-034) — 12-month purge boundary."""

import datetime as dt

import pytest

from takshashila_chatbot.domain.retention import purge_cutoff

pytestmark = pytest.mark.unit


def test_default_is_twelve_months_ago():
    assert purge_cutoff(dt.date(2026, 6, 16)) == dt.date(2025, 6, 16)


def test_custom_month_count():
    assert purge_cutoff(dt.date(2026, 6, 16), months=1) == dt.date(2026, 5, 16)


def test_clamps_to_end_of_shorter_month():
    # 12 months before a leap-day lands on Feb 28 of a non-leap year.
    assert purge_cutoff(dt.date(2028, 2, 29)) == dt.date(2027, 2, 28)
