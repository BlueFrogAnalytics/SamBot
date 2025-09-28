from pathlib import Path

import pytest

from samwatch.client import AttachmentDownload
from samwatch.config import Config
from samwatch.db import Database
from samwatch.ingest import IngestionOrchestrator


class StubClient:
    """Stub implementation of the SAM.gov client for tests."""

    def __init__(self) -> None:
        self.download_calls: list[Path] = []
        self.records = [
            {
                "noticeId": "TEST123",
                "title": "Test Notice",
                "agency": "Test Agency",
                "subTier": "Research",
                "office": "Procurement",
                "type": "solicitation",
                "status": "active",
                "postedDate": "2024-05-01",
                "updatedDate": "2024-05-02",
                "responseDate": "2024-05-15",
                "naics": ["541330"],
                "setAside": "none",
                "digest": "digest-1",
                "lastModified": "2024-05-02T12:00:00Z",
                "awards": [
                    {
                        "type": "award",
                        "date": "2024-05-01",
                        "description": "Initial award",
                        "amount": 1000,
                        "vendorName": "ACME",
                        "vendorDuns": "123456789",
                    }
                ],
                "contacts": [
                    {
                        "fullName": "Jane Doe",
                        "type": "primary",
                        "email": "jane@example.com",
                        "phone": "555-0100",
                    }
                ],
                "description": {"text": "Detailed body"},
                "resourceLinks": [
                    {
                        "url": "https://example.com/notice/TEST123/spec.pdf",
                        "fileName": "spec.pdf",
                        "sha256": "preseeded",
                        "size": 10,
                    }
                ],
            }
        ]

    def iter_search(self, params):  # pragma: no cover - exercised via orchestrator
        yield from self.records

    def download_attachment(self, url: str, destination: Path) -> AttachmentDownload:
        payload = b"attachment-bytes"
        destination.write_bytes(payload)
        self.download_calls.append(destination)
        return AttachmentDownload(
            url=url,
            path=destination,
            sha256="stub-sha",
            bytes_written=len(payload),
        )

    def fetch_description(self, url: str) -> str:
        return "Fetched description from URL"


@pytest.fixture()
def temp_config(tmp_path: Path) -> Config:
    data_dir = tmp_path / "data"
    sqlite_path = data_dir / "sqlite" / "test.db"
    files_dir = data_dir / "files"
    config = Config(
        api_key="test-key",
        data_dir=data_dir,
        sqlite_path=sqlite_path,
        files_dir=files_dir,
    )
    config.ensure_directories()
    return config


@pytest.fixture()
def database(temp_config: Config) -> Database:
    db = Database(temp_config.sqlite_path)
    db.initialize_schema()
    yield db
    db.close()


def test_hot_ingestion_records_data(temp_config: Config, database: Database) -> None:
    client = StubClient()
    orchestrator = IngestionOrchestrator(temp_config, client, database)

    orchestrator.run_hot()

    with database.cursor() as cur:
        cur.execute(
            "SELECT notice_id, title, naics_codes, set_aside FROM opportunities"
        )
        row = cur.fetchone()
        assert row["notice_id"] == "TEST123"
        assert row["title"] == "Test Notice"
        assert row["naics_codes"] == "541330"
        assert row["set_aside"] == "none"

        cur.execute("SELECT COUNT(*) FROM awards")
        assert cur.fetchone()[0] == 1

        cur.execute("SELECT COUNT(*) FROM contacts")
        assert cur.fetchone()[0] == 1

        cur.execute("SELECT body FROM descriptions")
        description = cur.fetchone()[0]
        assert "Detailed body" in description

        cur.execute("SELECT url, local_path, sha256, bytes FROM attachments")
        attachment = cur.fetchone()
        assert attachment["url"].endswith("spec.pdf")
        assert attachment["sha256"] == "stub-sha"
        assert attachment["bytes"] == len(b"attachment-bytes")

        cur.execute("SELECT metric, value FROM run_metrics")
        metrics = {row["metric"]: row["value"] for row in cur.fetchall()}
        assert metrics["records_processed"] == 1
        assert metrics["records_created"] == 1
        assert metrics["records_updated"] == 0
        assert metrics["attachments_downloaded"] == 1
        assert metrics["attachment_failures"] == 0

    stored_files = list((temp_config.files_dir / "TEST123").glob("*"))
    assert stored_files, "attachment should be written to disk"


def test_hot_ingestion_upserts_updates(temp_config: Config, database: Database) -> None:
    client = StubClient()
    orchestrator = IngestionOrchestrator(temp_config, client, database)

    orchestrator.run_hot()

    # mutate the digest to trigger an update path
    client.records[0]["digest"] = "digest-2"
    client.records[0].pop("description", None)
    orchestrator.run_hot()

    with database.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM opportunities")
        assert cur.fetchone()[0] == 1

        cur.execute("SELECT value FROM run_metrics WHERE metric = 'records_updated' ORDER BY id DESC LIMIT 1")
        updated_count = cur.fetchone()[0]
        assert updated_count >= 1

    assert len(client.download_calls) >= 2
