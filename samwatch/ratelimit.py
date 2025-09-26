"""Rate limiting utilities for SAMWatch."""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(slots=True)
class RateLimitBudget:
    """Represents the current and maximum capacity for a limit bucket."""

    limit: int
    remaining: int
    reset_epoch: float | None = None

    def update_from_headers(
        self,
        headers: Mapping[str, str],
        limit_header: str,
        remaining_header: str,
        reset_header: str,
    ) -> None:
        """Update the budget based on ``X-RateLimit`` headers."""

        if limit_header in headers:
            self.limit = int(headers[limit_header])
        if remaining_header in headers:
            self.remaining = int(headers[remaining_header])
        if reset_header in headers:
            try:
                self.reset_epoch = float(headers[reset_header])
            except ValueError:
                self.reset_epoch = None


class RateLimiter:
    """Coordinate access to the SAM.gov API respecting hourly and daily budgets."""

    def __init__(
        self,
        hourly_limit: int,
        daily_limit: int | None = None,
        *,
        time_fn: callable[[], float] = time.monotonic,
    ) -> None:
        self._lock = threading.Lock()
        self._time_fn = time_fn
        self.hourly = RateLimitBudget(limit=hourly_limit, remaining=hourly_limit)
        self.daily = (
            RateLimitBudget(limit=daily_limit, remaining=daily_limit)
            if daily_limit is not None
            else None
        )
        self._last_refresh = self._time_fn()

    def _refresh(self) -> None:
        now = self._time_fn()
        with self._lock:
            elapsed = now - self._last_refresh
            if elapsed >= 3600:
                self.hourly.remaining = self.hourly.limit
            if self.daily and elapsed >= 86400:
                self.daily.remaining = self.daily.limit
            if elapsed >= 3600 or (self.daily and elapsed >= 86400):
                self._last_refresh = now

    def acquire(self, tokens: int = 1, block: bool = True, timeout: float | None = None) -> bool:
        """Acquire tokens from the rate limiter."""

        deadline = None if timeout is None else self._time_fn() + timeout
        while True:
            self._refresh()
            with self._lock:
                if self.hourly.remaining >= tokens and (
                    self.daily is None or self.daily.remaining >= tokens
                ):
                    self.hourly.remaining -= tokens
                    if self.daily:
                        self.daily.remaining -= tokens
                    return True

                if not block:
                    return False

            if deadline is not None and self._time_fn() >= deadline:
                return False
            time.sleep(1)

    def update_from_headers(self, headers: Mapping[str, str]) -> None:
        """Update rate limit budgets based on response headers."""

        with self._lock:
            self.hourly.update_from_headers(
                headers,
                limit_header="X-RateLimit-Limit",
                remaining_header="X-RateLimit-Remaining",
                reset_header="X-RateLimit-Reset",
            )
            if self.daily:
                self.daily.update_from_headers(
                    headers,
                    limit_header="X-RateLimit-Limit-Day",
                    remaining_header="X-RateLimit-Remaining-Day",
                    reset_header="X-RateLimit-Reset-Day",
                )

    def record_retry_after(self, retry_after: float | None) -> None:
        """Sleep according to ``Retry-After`` header guidance."""

        if retry_after is None:
            return
        try:
            sleep_for = max(float(retry_after), 0.0)
        except ValueError:
            sleep_for = 0.0
        if sleep_for:
            time.sleep(sleep_for)
