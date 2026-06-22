"""Retention cutoff (FR-18, NFR-6, AC-9.3).

Computes the date before which question logs and leads are purged (default 12
months). Pure; the actual delete is performed by a retention store against today.
"""

from __future__ import annotations

import calendar
import datetime as dt


def purge_cutoff(today: dt.date, months: int = 12) -> dt.date:
    """Return the date ``months`` before ``today`` (day clamped to month length)."""
    total = today.year * 12 + (today.month - 1) - months
    year, month_index = divmod(total, 12)
    month = month_index + 1
    day = min(today.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)
