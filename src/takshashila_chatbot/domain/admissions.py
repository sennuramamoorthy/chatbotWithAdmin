"""Admission window status — self-computed from stored open/close dates.

Correct on the day asked even if no admin edited since the date passed (EC-3).
The close date is *inclusive*: admission is open through the end of that date
(AC-2.3 / EC-4). The LLM never compares dates — it only phrases this result.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum


class AdmissionState(str, Enum):
    UPCOMING = "upcoming"  # before the open date
    OPEN = "open"  # open_date <= today <= close_date (inclusive)
    CLOSED = "closed"  # after the close date


@dataclass(frozen=True)
class AdmissionStatus:
    state: AdmissionState
    open_date: dt.date
    close_date: dt.date

    @property
    def is_open(self) -> bool:
        return self.state is AdmissionState.OPEN


def admission_status(
    open_date: dt.date, close_date: dt.date, today: dt.date
) -> AdmissionStatus:
    """Compute admission status for ``today`` against the stored window.

    Raises ``ValueError`` if the window is invalid (close before open).
    """
    if close_date < open_date:
        raise ValueError("close_date must not be before open_date")

    if today < open_date:
        state = AdmissionState.UPCOMING
    elif today <= close_date:  # inclusive close
        state = AdmissionState.OPEN
    else:
        state = AdmissionState.CLOSED

    return AdmissionStatus(state=state, open_date=open_date, close_date=close_date)
