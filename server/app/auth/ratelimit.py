"""Counts failed attempts per key in a sliding window, in memory (one server process)."""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, status


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float, clock=time.monotonic) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _recent(self, key: str) -> deque[float]:
        failures = self._failures[key]
        cutoff = self._clock() - self._window
        while failures and failures[0] <= cutoff:
            failures.popleft()
        if not failures:
            del self._failures[key]
        return failures

    def check(self, key: str) -> None:
        """Raise 429 if `key` has used up its attempts."""
        failures = self._recent(key)
        if len(failures) >= self._limit:
            retry_after = max(1, int(failures[0] + self._window - self._clock()))
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "too many attempts; try again in a few minutes",
                headers={"Retry-After": str(retry_after)},
            )

    def fail(self, key: str) -> None:
        self._failures[key].append(self._clock())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
