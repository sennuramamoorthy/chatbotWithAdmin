"""Per-visitor rate limiting (FR-14). Covers TC-027, EC-19.

Deterministic via an injected FixedClock — no real sleeping.
"""

import datetime as dt

import pytest

from takshashila_chatbot.domain.clock import IST, FixedClock
from takshashila_chatbot.domain.rate_limit import RateLimiter

pytestmark = pytest.mark.unit


def _clock():
    return FixedClock(dt.datetime(2026, 6, 15, 12, 0, 0, tzinfo=IST))


def test_allows_up_to_per_minute_limit_then_blocks():  # TC-027
    clock = _clock()
    limiter = RateLimiter([(15, 60), (100, 3600)], clock)

    for _ in range(15):
        assert limiter.check("visitor").allowed is True

    result = limiter.check("visitor")  # 16th within the minute
    assert result.allowed is False
    assert result.retry_after > 0


def test_sliding_window_frees_up_after_window_passes():  # EC-19
    clock = _clock()
    limiter = RateLimiter([(15, 60), (100, 3600)], clock)

    for _ in range(15):
        limiter.check("visitor")
    assert limiter.check("visitor").allowed is False

    clock.advance(61)  # the first minute's events slide out of the 60s window
    assert limiter.check("visitor").allowed is True


def test_both_windows_enforced_independently():
    clock = _clock()
    limiter = RateLimiter([(2, 1), (3, 10)], clock)

    assert limiter.check("v").allowed is True  # 1
    assert limiter.check("v").allowed is True  # 2
    assert limiter.check("v").allowed is False  # 3 -> blocked by the 2-per-1s rule

    clock.advance(1.0)
    assert limiter.check("v").allowed is True  # 1s window cleared; 3rd accepted in 10s
    assert limiter.check("v").allowed is False  # blocked by the 3-per-10s rule

    clock.advance(9.5)  # earliest events leave the 10s window
    assert limiter.check("v").allowed is True


def test_requires_at_least_one_limit():
    with pytest.raises(ValueError):
        RateLimiter([], _clock())


def test_limits_are_per_key():
    clock = _clock()
    limiter = RateLimiter([(1, 60)], clock)

    assert limiter.check("a").allowed is True
    assert limiter.check("a").allowed is False
    assert limiter.check("b").allowed is True  # a different source is unaffected
