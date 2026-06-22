"""Clock abstraction.

Production code never calls ``datetime.now()`` directly — it depends on a
``Clock``. ``SystemClock`` is used at runtime; ``FixedClock`` makes every
date/time-boundary test deterministic. "Today" is always the *business* calendar
date in Asia/Kolkata, because the requirement's date rules (inclusive admission
close, fee due dates) are local-time statements.
"""

from __future__ import annotations

import datetime as dt
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


@runtime_checkable
class Clock(Protocol):
    """A source of the current instant and business-local calendar date."""

    def now(self) -> dt.datetime:  # timezone-aware
        ...

    def today(self) -> dt.date:  # business-local calendar date
        ...


class SystemClock:
    """Real wall-clock, expressed in the business timezone (default IST)."""

    def __init__(self, tz: ZoneInfo = IST) -> None:
        self._tz = tz

    def now(self) -> dt.datetime:
        return dt.datetime.now(self._tz)

    def today(self) -> dt.date:
        return self.now().date()


class FixedClock:
    """Deterministic clock for tests.

    Accepts an aware datetime (naive is assumed to already be in ``tz``). All
    reads are expressed in ``tz`` so ``today()`` reflects the business date.
    """

    def __init__(self, now: dt.datetime, tz: ZoneInfo = IST) -> None:
        if now.tzinfo is None:
            now = now.replace(tzinfo=tz)
        self._now = now
        self._tz = tz

    def now(self) -> dt.datetime:
        return self._now.astimezone(self._tz)

    def today(self) -> dt.date:
        return self.now().date()

    def advance(self, seconds: float) -> None:
        """Move the clock forward (test helper)."""
        self._now = self._now + dt.timedelta(seconds=seconds)
