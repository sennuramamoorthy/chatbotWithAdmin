"""Worker loop — ticks the scheduler and sleeps between ticks (deterministic)."""

import datetime as dt

import pytest

from takshashila_chatbot.application.scheduler import Scheduler
from takshashila_chatbot.domain.clock import IST, FixedClock
from takshashila_chatbot.worker import run_loop

pytestmark = pytest.mark.unit


def test_run_loop_ticks_and_sleeps():
    clock = FixedClock(dt.datetime(2026, 6, 16, 12, 0, tzinfo=IST))
    scheduler = Scheduler(clock)
    runs: list[int] = []
    scheduler.register("job", lambda: runs.append(1), interval_seconds=0)  # due every tick

    slept: list[float] = []
    run_loop(scheduler, ticks=3, sleep_seconds=30, sleeper=slept.append)

    assert len(runs) == 3
    assert slept == [30, 30, 30]
