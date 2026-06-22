"""Retention purge (FR-18, NFR-6, AC-9.3, TC-034).

Deletes question logs and leads older than the 12-month cutoff. The cutoff is the
deterministic ``purge_cutoff``; the deletes are delegated to two purgers.
"""

from __future__ import annotations

from ..domain.clock import Clock
from ..domain.retention import purge_cutoff
from .ports import Purger


class RetentionService:
    def __init__(
        self,
        question_purger: Purger,
        lead_purger: Purger,
        clock: Clock,
        *,
        months: int = 12,
    ) -> None:
        self._question_purger = question_purger
        self._lead_purger = lead_purger
        self._clock = clock
        self._months = months

    def purge(self) -> tuple[int, int]:
        """Return (questions_purged, leads_purged)."""
        cutoff = purge_cutoff(self._clock.today(), self._months)
        return (
            self._question_purger.purge_before(cutoff),
            self._lead_purger.purge_before(cutoff),
        )
