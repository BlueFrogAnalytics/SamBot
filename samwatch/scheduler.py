"""Simple cooperative scheduler with runtime metrics."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .metrics import SchedulerMetricsRecorder

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ScheduledJob:
    """A single scheduled action."""

    name: str
    interval: timedelta
    action: Callable[[], None]


@dataclass(slots=True)
class JobMetrics:
    """Runtime metrics tracked for each scheduled job."""

    runs_started: int = 0
    runs_succeeded: int = 0
    runs_failed: int = 0
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "runs_started": self.runs_started,
            "runs_succeeded": self.runs_succeeded,
            "runs_failed": self.runs_failed,
            "last_started_at": self.last_started_at.isoformat()
            if self.last_started_at
            else None,
            "last_finished_at": self.last_finished_at.isoformat()
            if self.last_finished_at
            else None,
            "last_error": self.last_error,
        }


class Scheduler:
    """Coordinate periodic execution of ingestion tasks."""

    def __init__(self, metrics_recorder: "SchedulerMetricsRecorder | None" = None) -> None:
        self._jobs: list[ScheduledJob] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._metrics: dict[str, JobMetrics] = {}
        self._metrics_recorder = metrics_recorder

    def add_job(self, job: ScheduledJob) -> None:
        with self._lock:
            self._jobs.append(job)
            self._metrics.setdefault(job.name, JobMetrics())
            logger.info("Scheduled job %s to run every %s", job.name, job.interval)
            if self._metrics_recorder is not None:
                self._metrics_recorder.register_job(job)

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
                    metrics = self._metrics.setdefault(job.name, JobMetrics())
                    metrics.runs_started += 1
                    metrics.last_started_at = datetime.now(UTC)
                    start_time = time.monotonic()
                    if self._metrics_recorder is not None:
                        self._metrics_recorder.record_job_start(job)
                    try:
                        job.action()
                    except Exception as exc:  # pragma: no cover - defensive logging
                        logger.exception("Job %s raised an exception", job.name)
                        metrics.runs_failed += 1
                        metrics.last_error = "exception"
                        if self._metrics_recorder is not None:
                            duration = time.monotonic() - start_time
                            self._metrics_recorder.record_job_failure(job, duration, exc)
                    else:
                        metrics.runs_succeeded += 1
                        metrics.last_error = None
                        if self._metrics_recorder is not None:
                            duration = time.monotonic() - start_time
                            self._metrics_recorder.record_job_success(job, duration)
                    finally:
                        metrics.last_finished_at = datetime.now(UTC)
                        next_run[job.name] = now + job.interval.total_seconds()
            time.sleep(1)

    def stop(self) -> None:
        self._stop_event.set()

    def metrics_snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {name: metrics.to_dict() for name, metrics in self._metrics.items()}
