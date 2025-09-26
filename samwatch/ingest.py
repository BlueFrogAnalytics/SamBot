"""Ingestion routines for SAMWatch."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Iterable, Mapping

from .client import SAMWatchClient
from .config import Config
from .db import Database

logger = logging.getLogger(__name__)


class IngestionOrchestrator:
    """Coordinate ingestion sweeps against the SAM.gov API."""

    def __init__(self, config: Config, client: SAMWatchClient, database: Database) -> None:
        self.config = config
        self.client = client
        self.database = database

    def run_hot(self) -> None:
        """Scan the current day for new or updated notices."""

        today = datetime.utcnow().date()
        params = {
            "postedFrom": today.isoformat(),
            "postedTo": today.isoformat(),
            "offset": 0,
        }
        self._ingest_range(params)

    def run_warm(self, days: int = 7) -> None:
        """Rescan the last ``days`` for amendments or cancellations."""

        end = datetime.utcnow().date()
        start = end - timedelta(days=days)
        params = {
            "postedFrom": start.isoformat(),
            "postedTo": end.isoformat(),
            "offset": 0,
        }
        self._ingest_range(params)

    def run_cold(self, start: datetime, end: datetime) -> None:
        """Perform a cold sweep over a longer window."""

        if (end - start).days > 365:
            raise ValueError("Cold sweep window cannot exceed one year")
        params = {
            "postedFrom": start.date().isoformat(),
            "postedTo": end.date().isoformat(),
            "offset": 0,
        }
        self._ingest_range(params)

    def _ingest_range(self, params: Mapping[str, object]) -> None:
        logger.info("Starting ingestion with params %s", params)
        for record in self.client.iter_search(params):
            self.upsert_record(record)

    def upsert_record(self, record: Mapping[str, object]) -> None:
        """Persist a single API record into the database."""

        notice_id = str(record.get("noticeId"))
        logger.debug("Processing notice %s", notice_id)
        naics = record.get("naics", []) or []
        if isinstance(naics, str):
            naics_codes = naics
        else:
            naics_codes = ",".join(str(code) for code in naics)

        with self.database.cursor() as cur:
            cur.execute(
                """
                INSERT INTO opportunities (
                    notice_id, title, agency, sub_tier, office, notice_type, status,
                    posted_at, updated_at, response_deadline, naics_codes, set_aside, digest, last_changed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(notice_id) DO UPDATE SET
                    title=excluded.title,
                    agency=excluded.agency,
                    sub_tier=excluded.sub_tier,
                    office=excluded.office,
                    notice_type=excluded.notice_type,
                    status=excluded.status,
                    posted_at=excluded.posted_at,
                    updated_at=excluded.updated_at,
                    response_deadline=excluded.response_deadline,
                    naics_codes=excluded.naics_codes,
                    set_aside=excluded.set_aside,
                    digest=excluded.digest,
                    last_seen_at=CURRENT_TIMESTAMP,
                    last_changed_at=CASE
                        WHEN excluded.digest IS NOT opportunities.digest THEN CURRENT_TIMESTAMP
                        ELSE opportunities.last_changed_at
                    END
                ;
                """,
                (
                    notice_id,
                    record.get("title"),
                    record.get("agency"),
                    record.get("subTier"),
                    record.get("office"),
                    record.get("type"),
                    record.get("status"),
                    record.get("postedDate"),
                    record.get("updatedDate"),
                    record.get("responseDate"),
                    naics_codes,
                    record.get("setAside"),
                    record.get("digest"),
                    record.get("lastModified"),
                ),
            )

            cur.execute("SELECT id FROM opportunities WHERE notice_id = ?", (notice_id,))
            row = cur.fetchone()
            if row is None:
                return
            opportunity_id = row[0]

            self._persist_contacts(cur, opportunity_id, record.get("contacts", []))
            self._persist_attachments(cur, opportunity_id, record.get("resourceLinks", []))

    def _persist_contacts(self, cur, opportunity_id: int, contacts: Iterable[Mapping[str, object]]) -> None:
        cur.execute("DELETE FROM contacts WHERE opportunity_id = ?", (opportunity_id,))
        for contact in contacts or []:
            cur.execute(
                """
                INSERT INTO contacts (opportunity_id, name, type, email, phone)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    opportunity_id,
                    contact.get("fullName"),
                    contact.get("type"),
                    contact.get("email"),
                    contact.get("phone"),
                ),
            )

    def _persist_attachments(
        self, cur, opportunity_id: int, attachments: Iterable[Mapping[str, object]]
    ) -> None:
        cur.execute("DELETE FROM attachments WHERE opportunity_id = ?", (opportunity_id,))
        for attachment in attachments or []:
            url = attachment.get("url") or attachment.get("href")
            if not url:
                continue
            cur.execute(
                """
                INSERT INTO attachments (opportunity_id, url, local_path, sha256, bytes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    opportunity_id,
                    url,
                    attachment.get("fileName", ""),
                    attachment.get("sha256"),
                    attachment.get("size"),
                ),
            )
