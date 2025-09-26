"""Historical backfill planning for SAMWatch."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterator

from .config import Config


@dataclass(slots=True)
class BackfillWindow:
    start: date
    end: date


class BackfillPlanner:
    """Generate windows for cold sweeps without violating API limits."""

    def __init__(self, config: Config, window_days: int = 30) -> None:
        if window_days <= 0:
            raise ValueError("window_days must be positive")
        if window_days > 365:
            raise ValueError("window_days cannot exceed 365")
        self.config = config
        self.window_days = window_days

    def plan(self, start: date, end: date) -> Iterator[BackfillWindow]:
        """Yield windows to cover the requested date range."""

        if start > end:
            raise ValueError("start must be before end")

        current = start
        while current <= end:
            window_end = min(current + timedelta(days=self.window_days - 1), end)
            yield BackfillWindow(start=current, end=window_end)
            current = window_end + timedelta(days=1)

    def next_window_from_db(self, last_recorded: datetime | None) -> BackfillWindow:
        """Return the next window to process based on persisted metadata."""

        today = datetime.utcnow().date()
        if last_recorded is None:
            start = today - timedelta(days=self.window_days)
        else:
            start = last_recorded.date() + timedelta(days=1)
        end = min(start + timedelta(days=self.window_days - 1), today)
        return BackfillWindow(start=start, end=end)
