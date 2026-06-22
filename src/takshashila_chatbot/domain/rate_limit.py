"""Per-visitor rate limiting (FR-14).

Sliding-window-log limiter supporting multiple windows simultaneously
(e.g. 15/min *and* 100/hour). Deterministic via an injected ``Clock``.

This in-memory implementation backs unit tests and single-node use; production
uses the same ``check()`` contract over a shared Redis store so counters are
consistent across stateless API replicas.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from .clock import Clock


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after: float = 0.0  # seconds until the next request would be allowed
    limit: int | None = None  # the max_count of the window that was hit


class RateLimiter:
    def __init__(self, limits: list[tuple[int, int]], clock: Clock) -> None:
        if not limits:
            raise ValueError("at least one (max_count, window_seconds) limit required")
        # Evaluate from the shortest window to the longest.
        self._limits = sorted(limits, key=lambda lw: lw[1])
        self._max_window = max(window for _, window in limits)
        self._clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> RateLimitResult:
        """Attempt one request for ``key``; records it iff allowed."""
        now = self._clock.now().timestamp()
        events = self._events[key]

        # Drop events older than the largest window.
        cutoff = now - self._max_window
        while events and events[0] <= cutoff:
            events.popleft()

        for max_count, window in self._limits:
            window_start = now - window
            in_window = [t for t in events if t > window_start]
            if len(in_window) >= max_count:
                oldest = in_window[0]
                retry_after = oldest + window - now
                return RateLimitResult(
                    allowed=False, retry_after=max(retry_after, 0.0), limit=max_count
                )

        events.append(now)
        return RateLimitResult(allowed=True)
