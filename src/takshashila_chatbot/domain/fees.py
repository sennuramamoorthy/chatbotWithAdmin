"""Fee due-date status — upcoming / due today / overdue (AC-2.4, EC-5).

Computed from the stored due date against today; never stored, never LLM-guessed.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum


class FeeState(str, Enum):
    UPCOMING = "upcoming"
    DUE_TODAY = "due_today"
    OVERDUE = "overdue"


@dataclass(frozen=True)
class FeeStatus:
    state: FeeState
    due_date: dt.date
    days_until_due: int  # >0 upcoming, 0 due today, <0 overdue (by abs days)


def fee_status(due_date: dt.date, today: dt.date) -> FeeStatus:
    """Compute fee status for ``today`` against the stored due date."""
    days_until_due = (due_date - today).days

    if days_until_due > 0:
        state = FeeState.UPCOMING
    elif days_until_due == 0:
        state = FeeState.DUE_TODAY
    else:
        state = FeeState.OVERDUE

    return FeeStatus(state=state, due_date=due_date, days_until_due=days_until_due)
