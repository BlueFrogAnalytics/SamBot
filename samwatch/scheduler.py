"""Simple in-process scheduler for recurring SAMWatch jobs."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ScheduledJob:
    name: str
    interval: timedelta
    action: Callable[[], None]


class Scheduler:
    """Coordinate periodic execution of ingestion tasks."""

    def __init__(self) -> None:
        self._jobs: list[ScheduledJob] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    def add_job(self, job: ScheduledJob) -> None:
        with self._lock:
            self._jobs.append(job)
            logger.info("Scheduled job %s to run every %s", job.name, job.interval)

    def run(self) -> None:
        """Run scheduled jobs until stopped."""

        next_run: dict[str, float] = {}
        while not self._stop_event.is_set():
            now = time.monotonic()
            with self._lock:
                jobs = list(self._jobs)
            for job in jobs:
                due_at = next_run.get(job.name, now)
                if now >= due_at:
                    logger.debug("Executing job %s", job.name)
                    try:
                        job.action()
                    except Exception:  # pragma: no cover - defensive logging
                        logger.exception("Job %s raised an exception", job.name)
                    next_run[job.name] = now + job.interval.total_seconds()
            time.sleep(1)

    def stop(self) -> None:
        self._stop_event.set()
