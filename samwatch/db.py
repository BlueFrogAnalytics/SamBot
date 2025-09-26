"""Database helpers for the SAMWatch service."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
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
