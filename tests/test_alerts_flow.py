from pathlib import Path

import pytest

from samwatch.alerts import AlertEngine
from samwatch.config import Config
from samwatch.db import Database


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
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO opportunities (
                notice_id, title, agency, sub_tier, office, notice_type, status,
                posted_at, updated_at, response_deadline, naics_codes, set_aside,
                digest, last_changed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "TEST123",
                "Test Opportunity",
                "Test Agency",
                "Research",
                "Procurement",
                "solicitation",
                "active",
                "2024-05-01",
                "2024-05-02",
                "2024-05-15",
                "541330",
                "none",
                "digest-1",
                "2024-05-02T12:00:00Z",
            ),
        )
    yield db
    db.close()


def test_alert_engine_persists_and_reuses_matches(temp_config: Config, database: Database) -> None:
    engine = AlertEngine(temp_config, database)

    rule_id: int | None = None
    with database.cursor() as cur:
        cur.execute(
            """
            INSERT INTO rules (name, description, kind, definition, is_active)
            VALUES (?, ?, ?, ?, 1)
            """,
            (
                "Test Rule",
                "Matches the seeded opportunity",
                "sql",
                "SELECT id AS opportunity_id FROM opportunities WHERE notice_id = 'TEST123'",
            ),
        )
        rule_id = cur.lastrowid
        cur.execute(
            "INSERT INTO alerts (rule_id, delivery_method, target) VALUES (?, ?, ?)",
            (rule_id, "cli", "{}"),
        )

    engine.evaluate_rules()
    engine.evaluate_rules()

    assert rule_id is not None
    with database.cursor() as cur:
        cur.execute(
            "SELECT opportunity_id, payload FROM rule_matches WHERE rule_id = ?",
            (rule_id,),
        )
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0]["opportunity_id"] == 1
        assert rows[0]["payload"] is None

        cur.execute("SELECT COUNT(*) FROM alerts WHERE rule_id = ?", (rule_id,))
        assert cur.fetchone()[0] == 1

