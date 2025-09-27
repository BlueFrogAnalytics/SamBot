"""Metrics exporters for SAMWatch."""

from __future__ import annotations

import threading
import time
from typing import Any

from prometheus_client import Counter, Gauge, Info, start_http_server

from .scheduler import ScheduledJob


class SchedulerMetricsRecorder:
    """Interface for receiving scheduler lifecycle events."""

    def register_job(self, job: ScheduledJob) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def record_job_start(self, job: ScheduledJob) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def record_job_success(self, job: ScheduledJob, duration: float) -> None:  # pragma: no cover
        raise NotImplementedError

    def record_job_failure(
        self, job: ScheduledJob, duration: float, error: BaseException | None = None
    ) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class PrometheusSchedulerMetrics(SchedulerMetricsRecorder):
    """Expose scheduler metrics via a Prometheus scrape endpoint."""

    def __init__(self, *, host: str = "0.0.0.0", port: int = 9464) -> None:
        self._host = host
        self._port = port
        self._started = False
        self._lock = threading.Lock()

        self._runs_started = Counter(
            "samwatch_scheduler_runs_started_total",
            "Number of times a job started execution.",
            labelnames=("job",),
        )
        self._runs_succeeded = Counter(
            "samwatch_scheduler_runs_succeeded_total",
            "Number of times a job completed successfully.",
            labelnames=("job",),
        )
        self._runs_failed = Counter(
            "samwatch_scheduler_runs_failed_total",
            "Number of times a job raised an exception.",
            labelnames=("job",),
        )
        self._last_started = Gauge(
            "samwatch_scheduler_last_started_timestamp",
            "Unix timestamp for the most recent start of a job.",
            labelnames=("job",),
        )
        self._last_finished = Gauge(
            "samwatch_scheduler_last_finished_timestamp",
            "Unix timestamp for the most recent completion of a job.",
            labelnames=("job",),
        )
        self._last_duration = Gauge(
            "samwatch_scheduler_last_duration_seconds",
            "Duration of the most recent job execution in seconds.",
            labelnames=("job",),
        )
        self._last_status = Gauge(
            "samwatch_scheduler_last_status",
            "Status of the last run (1=success, 0=running, -1=failure).",
            labelnames=("job",),
        )
        self._last_error = Info(
            "samwatch_scheduler_last_error",
            "Last error message recorded for a job (empty if none).",
            labelnames=("job",),
        )

    def start(self) -> None:
        """Start the HTTP server if it has not already been started."""

        with self._lock:
            if not self._started:
                start_http_server(self._port, addr=self._host)
                self._started = True

    def register_job(self, job: ScheduledJob) -> None:
        labels = {"job": job.name}
        self._runs_started.labels(**labels)
        self._runs_succeeded.labels(**labels)
        self._runs_failed.labels(**labels)
        self._last_started.labels(**labels).set(float("nan"))
        self._last_finished.labels(**labels).set(float("nan"))
        self._last_duration.labels(**labels).set(float("nan"))
        self._last_status.labels(**labels).set(0.0)
        self._last_error.labels(**labels).info({"message": ""})

    def record_job_start(self, job: ScheduledJob) -> None:
        labels = {"job": job.name}
        now = time.time()
        self._runs_started.labels(**labels).inc()
        self._last_started.labels(**labels).set(now)
        self._last_status.labels(**labels).set(0.0)

    def record_job_success(self, job: ScheduledJob, duration: float) -> None:
        labels = {"job": job.name}
        now = time.time()
        self._runs_succeeded.labels(**labels).inc()
        self._last_finished.labels(**labels).set(now)
        self._last_duration.labels(**labels).set(duration)
        self._last_status.labels(**labels).set(1.0)
        self._last_error.labels(**labels).info({"message": ""})

    def record_job_failure(
        self, job: ScheduledJob, duration: float, error: BaseException | None = None
    ) -> None:
        labels = {"job": job.name}
        now = time.time()
        self._runs_failed.labels(**labels).inc()
        self._last_finished.labels(**labels).set(now)
        self._last_duration.labels(**labels).set(duration)
        self._last_status.labels(**labels).set(-1.0)
        message = str(error) if error else ""
        self._last_error.labels(**labels).info({"message": message[:200]})

    def metrics_details(self) -> dict[str, Any]:
        """Return a snapshot of metric labels for inspection or testing."""

        # Note: prometheus_client does not expose direct value access; this helper
        # exists primarily so unit tests can assert that jobs have been registered.
        return {
            "host": self._host,
            "port": self._port,
            "started": self._started,
        }
