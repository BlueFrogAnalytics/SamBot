"""Command line interface for SAMWatch."""

from __future__ import annotations

import json
from datetime import datetime

import typer

from .alerts import AlertEngine
from .backfill import BackfillPlanner
from .client import SAMWatchClient
from .config import Config, ConfigError
from .db import Database
from .ingest import IngestionOrchestrator
from .refresher import Refresher

app = typer.Typer(help="Utilities for operating the SAMWatch service")


def _build_context(with_client: bool = True) -> tuple[Config, Database, SAMWatchClient | None]:
    config = Config.from_env()
    database = Database(config.sqlite_path)
    database.initialize_schema()
    client = SAMWatchClient(config) if with_client else None
    return config, database, client


@app.command()
def run(
    hot: bool = typer.Option(False, help="Run the hot beam (today's notices)"),
    warm: bool = typer.Option(False, help="Run the warm beam (recent notices)"),
    cold_start: str | None = typer.Option(None, help="Cold sweep start date YYYY-MM-DD"),
    cold_end: str | None = typer.Option(None, help="Cold sweep end date YYYY-MM-DD"),
) -> None:
    """Execute ingestion sweeps."""

    config, database, client = _build_context(with_client=True)
    assert client is not None
    orchestrator = IngestionOrchestrator(config, client, database)

    try:
        if hot:
            orchestrator.run_hot()
        if warm:
            orchestrator.run_warm()
        if cold_start and cold_end:
            start = datetime.fromisoformat(cold_start)
            end = datetime.fromisoformat(cold_end)
            orchestrator.run_cold(start, end)
    finally:
        client.close()
        database.close()


@app.command()
def backfill(
    start: str = typer.Argument(..., help="Start date YYYY-MM-DD"),
    end: str = typer.Argument(..., help="End date YYYY-MM-DD"),
    window_days: int = typer.Option(30, help="Number of days per cold sweep window"),
) -> None:
    """Plan backfill windows for historical sweeps."""

    config, database, client = _build_context(with_client=False)
    try:
        planner = BackfillPlanner(config, window_days=window_days)
        start_date = datetime.fromisoformat(start).date()
        end_date = datetime.fromisoformat(end).date()
        for window in planner.plan(start_date, end_date):
            typer.echo(f"{window.start.isoformat()} -> {window.end.isoformat()}")
    finally:
        database.close()
        if client:
            client.close()


@app.command()
def query(sql: str = typer.Argument(..., help="SQL statement to run")) -> None:
    """Run raw SQL against the SQLite database."""

    config, database, client = _build_context(with_client=True)
    assert client is not None
    try:
        cursor = database.execute(sql)
        rows = cursor.fetchall()
        typer.echo(json.dumps([dict(row) for row in rows], indent=2))
    finally:
        client.close()
        database.close()


@app.command()
def status() -> None:
    """Print a quick status summary."""

    config, database, client = _build_context(with_client=True)
    assert client is not None
    try:
        cursor = database.execute(
            "SELECT COUNT(*) AS count FROM opportunities",
        )
        row = cursor.fetchone()
        total = row[0] if row else 0
        typer.echo(f"Opportunities: {total}")
    finally:
        client.close()
        database.close()


@app.command()
def refresh(notice_id: str = typer.Argument(..., help="Notice ID to refresh")) -> None:
    """Refresh a single opportunity from the API."""

    config, database, client = _build_context(with_client=True)
    assert client is not None
    try:
        refresher = Refresher(config, client, database)
        refresher.refresh_opportunity(notice_id)
    finally:
        client.close()
        database.close()


@app.command()
def alerts() -> None:
    """Evaluate all pursuit rules and persist matches."""

    config, database, client = _build_context(with_client=False)
    try:
        engine = AlertEngine(database)
        engine.evaluate_rules()
    finally:
        database.close()
        if client:
            client.close()


def main() -> None:  # pragma: no cover - CLI entry point
    try:
        app()
    except ConfigError as exc:
        typer.echo(f"Configuration error: {exc}")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":  # pragma: no cover
    main()
