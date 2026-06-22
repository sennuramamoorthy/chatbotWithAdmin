"""Deterministic interval scheduler for background jobs.

Background workers run periodic jobs (dead-end clustering, 12-month retention)
by registering them here and calling :meth:`Scheduler.tick` on their own loop.
The scheduler owns *when* a job is due, never *how often* the loop spins — it is
driven entirely by the injected :class:`~takshashila_chatbot.domain.clock.Clock`,
so ``tick()`` never sleeps and tests advance time with ``FixedClock.advance``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from takshashila_chatbot.domain.clock import Clock


@dataclass
class _Job:
    fn: Callable[[], None]
    interval_seconds: float
    last_run: float | None = None


@dataclass
class Scheduler:
    """Runs registered jobs at fixed intervals, paced by a :class:`Clock`."""

    clock: Clock
    _jobs: dict[str, _Job] = field(default_factory=dict)

    def register(
        self, name: str, fn: Callable[[], None], interval_seconds: float
    ) -> None:
        """Register ``fn`` to run every ``interval_seconds`` under ``name``."""
        self._jobs[name] = _Job(fn=fn, interval_seconds=interval_seconds)

    def tick(self) -> list[str]:
        """Run every due job and return the names of the jobs that ran.

        A job is due if it has never run, or if at least ``interval_seconds``
        have elapsed since its last run. Each job that runs has its ``fn``
        invoked and its ``last_run`` set to the current timestamp.
        """
        now = self.clock.now().timestamp()
        ran: list[str] = []
        for name, job in self._jobs.items():
            if job.last_run is None or (now - job.last_run) >= job.interval_seconds:
                job.fn()
                job.last_run = now
                ran.append(name)
        return ran
