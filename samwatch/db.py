"""Database helpers for the SAMWatch service."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_STATEMENTS: Sequence[str] = (
    """
    PRAGMA foreign_keys = ON;
    """,
    """
    CREATE TABLE IF NOT EXISTS opportunities (
        id INTEGER PRIMARY KEY,
        notice_id TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        agency TEXT,
        sub_tier TEXT,
        office TEXT,
        notice_type TEXT,
        status TEXT,
        posted_at TEXT,
        updated_at TEXT,
        response_deadline TEXT,
        naics_codes TEXT,
        set_aside TEXT,
        digest TEXT,
        last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_changed_at TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS awards (
        id INTEGER PRIMARY KEY,
        opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
        award_type TEXT,
        date TEXT,
        description TEXT,
        amount REAL,
        vendor_name TEXT,
        vendor_duns TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS contacts (
        id INTEGER PRIMARY KEY,
        opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
        name TEXT,
        type TEXT,
        email TEXT,
        phone TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS descriptions (
        id INTEGER PRIMARY KEY,
        opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
        body TEXT NOT NULL,
        fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS attachments (
        id INTEGER PRIMARY KEY,
        opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
        url TEXT NOT NULL,
        local_path TEXT NOT NULL,
        sha256 TEXT,
        bytes INTEGER,
        downloaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY,
        kind TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        status TEXT NOT NULL,
        error_message TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS rules (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        kind TEXT NOT NULL,
        definition TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY,
        rule_id INTEGER NOT NULL REFERENCES rules(id) ON DELETE CASCADE,
        delivery_method TEXT NOT NULL,
        target TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS rule_matches (
        id INTEGER PRIMARY KEY,
        rule_id INTEGER NOT NULL REFERENCES rules(id) ON DELETE CASCADE,
        opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
        matched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        payload TEXT,
        UNIQUE(rule_id, opportunity_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS run_metrics (
        id INTEGER PRIMARY KEY,
        run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
        metric TEXT NOT NULL,
        value INTEGER NOT NULL,
        recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS opportunity_search USING fts5(
        title, agency, body, content='descriptions', content_rowid='opportunity_id'
    );
    """,
    """
    CREATE TRIGGER IF NOT EXISTS descriptions_ai AFTER INSERT ON descriptions
    BEGIN
        INSERT INTO opportunity_search(rowid, title, agency, body)
        SELECT
            NEW.opportunity_id,
            o.title,
            o.agency,
            NEW.body
        FROM opportunities o
        WHERE o.id = NEW.opportunity_id;
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS descriptions_ad AFTER DELETE ON descriptions
    BEGIN
        DELETE FROM opportunity_search WHERE rowid = OLD.opportunity_id;
    END;
    """,
)


class Database:
    """Convenience wrapper around :mod:`sqlite3` with schema helpers."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._connection: sqlite3.Connection | None = None

    @staticmethod
    def _timestamp() -> str:
        """Return a UTC timestamp in ISO 8601 format."""

        return (
            datetime.now(UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def connect(self) -> sqlite3.Connection:
        if self._connection is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.path)
            self._connection.row_factory = sqlite3.Row
        return self._connection

    @property
    def connection(self) -> sqlite3.Connection:
        return self.connect()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def initialize_schema(self) -> None:
        conn = self.connect()
        with conn:
            for statement in SCHEMA_STATEMENTS:
                conn.execute(statement)

    @contextmanager
    def cursor(self) -> Iterator[sqlite3.Cursor]:
        conn = self.connect()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        finally:
            cur.close()

    def executemany(self, sql: str, seq_of_parameters: Iterable[Iterable[object]]) -> None:
        with self.cursor() as cur:
            cur.executemany(sql, seq_of_parameters)

    def execute(self, sql: str, parameters: Iterable[object] | None = None) -> sqlite3.Cursor:
        conn = self.connect()
        cur = conn.execute(sql, tuple(parameters or ()))
        conn.commit()
        return cur

    @contextmanager
    def record_run(self, kind: str) -> Iterator[int]:
        """Context manager that records a run in the ``runs`` table."""

        started_at = self._timestamp()
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO runs (kind, started_at, status)
                VALUES (?, ?, ?)
                """,
                (kind, started_at, "running"),
            )
            run_id = int(cur.lastrowid)
        try:
            yield run_id
        except Exception as exc:  # pragma: no cover - defensive logging
            self._finalize_run(run_id, status="failed", error_message=str(exc)[:1000])
            raise
        else:
            self._finalize_run(run_id, status="succeeded")

    def _finalize_run(
        self,
        run_id: int,
        *,
        status: str,
        error_message: str | None = None,
    ) -> None:
        with self.cursor() as cur:
            cur.execute(
                """
                UPDATE runs
                SET status = ?, finished_at = ?, error_message = ?
                WHERE id = ?
                """,
                (status, self._timestamp(), error_message, run_id),
            )

    def record_run_metrics(self, run_id: int, metrics: Mapping[str, int]) -> None:
        """Persist aggregated metrics for a completed run."""

        rows = [
            (run_id, key, int(value))
            for key, value in metrics.items()
            if value is not None
        ]
        if not rows:
            return
        with self.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO run_metrics (run_id, metric, value)
                VALUES (?, ?, ?)
                """,
                rows,
            )
