"""Interval scheduler — deterministic, clock-driven job dispatch."""

import datetime as dt

import pytest

from takshashila_chatbot.application.scheduler import Scheduler
from takshashila_chatbot.domain.clock import IST, FixedClock

pytestmark = pytest.mark.unit


def _clock() -> FixedClock:
    return FixedClock(dt.datetime(2026, 1, 1, 9, 0, 0, tzinfo=IST))


def test_first_tick_runs_all_jobs_once():
    clock = _clock()
    sched = Scheduler(clock)
    calls: list[str] = []
    sched.register("clustering", lambda: calls.append("clustering"), 60.0)
    sched.register("retention", lambda: calls.append("retention"), 3600.0)

    ran = sched.tick()

    assert ran == ["clustering", "retention"]
    assert calls == ["clustering", "retention"]


def test_immediate_second_tick_runs_nothing():
    clock = _clock()
    sched = Scheduler(clock)
    calls: list[str] = []
    sched.register("clustering", lambda: calls.append("clustering"), 60.0)

    assert sched.tick() == ["clustering"]
    assert sched.tick() == []  # no clock advance -> nothing due
    assert calls == ["clustering"]


def test_job_runs_again_after_interval_elapses():
    clock = _clock()
    sched = Scheduler(clock)
    calls: list[str] = []
    sched.register("clustering", lambda: calls.append("clustering"), 60.0)

    sched.tick()
    clock.advance(60.0)  # exactly at the boundary -> due
    ran = sched.tick()

    assert ran == ["clustering"]
    assert calls == ["clustering", "clustering"]


def test_only_due_job_runs_when_intervals_differ():
    clock = _clock()
    sched = Scheduler(clock)
    calls: list[str] = []
    sched.register("clustering", lambda: calls.append("clustering"), 60.0)
    sched.register("retention", lambda: calls.append("retention"), 3600.0)

    sched.tick()  # both run on first tick
    clock.advance(60.0)  # past clustering's interval, not retention's
    ran = sched.tick()

    assert ran == ["clustering"]  # only the due job
    assert calls == ["clustering", "retention", "clustering"]
