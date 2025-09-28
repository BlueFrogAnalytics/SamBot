"""Utilities for refreshing stored opportunity data."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from .client import SAMWatchClient
from .config import Config
from .db import Database
from .ingest import IngestionOrchestrator

logger = logging.getLogger(__name__)


class Refresher:
    """Handles rescans of existing opportunities."""

    def __init__(self, config: Config, client: SAMWatchClient, database: Database) -> None:
        self.config = config
        self.client = client
        self.database = database
        self._ingestor = IngestionOrchestrator(config, client, database)

    def refresh_opportunity(self, notice_id: str) -> None:
        logger.info("Refreshing opportunity %s", notice_id)
        data = self.client.search_opportunities({"noticeId": notice_id, "limit": 1})
        records = data.get("opportunitiesData", [])
        if not records:
            logger.warning("No data returned for notice %s", notice_id)
            return
        record = records[0]
        self._ingestor.upsert_record(record)

    def refresh_recent(self, hours: int = 24) -> None:
        window_start = datetime.now(UTC) - timedelta(hours=hours)
        iso_start = window_start.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        logger.info("Refreshing opportunities changed since %s", iso_start)
        data = self.client.search_opportunities({"modifiedFrom": iso_start})
        for record in data.get("opportunitiesData", []):
            notice_id = record.get("noticeId")
            if notice_id:
                self._ingestor.upsert_record(record)
