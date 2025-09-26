# SAMWatch

SAMWatch is a Python service that continuously monitors SAM.gov opportunities, stores rich
metadata in SQLite with full-text search, and generates alerts that match pursuit criteria.
This repository houses the scaffolding for the service, including configuration utilities,
rate limiting primitives, an HTTP client, and database schema definitions.

## Features

- Dataclass-based configuration loader that reads environment variables
- Rate limiter that tracks hourly and daily SAM.gov API budgets
- HTTP client helpers for searching opportunities, retrieving descriptions, and downloading
  attachments
- SQLite schema with tables for opportunities, contacts, attachments, and alerting rules
- Typer-based command line interface for running ingestion pipelines, scheduling loops, and
  querying persisted data
- Run tracking persisted in the SQLite `runs` table with per-run metrics
- Multi-channel alerting engine that can emit matches via CLI, webhooks, or email

## Getting Started

1. Install the project in editable mode:

   ```bash
   pip install -e .[dev]
   ```

2. Export your SAM.gov API key:

   ```bash
   export SAM_API_KEY="your-key-here"
   ```

3. Run the hot ingestion loop:

   ```bash
   samwatch run --hot
   ```

4. To operate continuously, launch the scheduler which orchestrates the hot, warm, and refresh
   sweeps alongside health checks:

   ```bash
   samwatch serve
   ```

## Development

- Configure formatting and linting with `ruff` using the settings in `pyproject.toml`.
- Tests can be added under `tests/` and run with `pytest`.
- See `docs/sql_guide.md` for example analytical queries against the SQLite database.

## Roadmap

This repository currently includes the foundational scaffolding for SAMWatch. Upcoming work
includes implementing full ingestion pipelines, attachment handling, alert delivery
integrations, and operational documentation.

## Configuring Alerts

Alert rules live in the `rules` table and can be evaluated with `samwatch alerts`. Each rule may
have one or more entries in the `alerts` table to control delivery. Supported delivery methods are:

- `cli`/`console`: render matches in a rich table in the terminal.
- `webhook`: POST JSON payloads to a remote endpoint. The `target` column should contain either the
  URL as a string or a JSON object such as `{"url": "https://example.com/webhook", "headers": {"Authorization": "token"}}`.
- `email`: send matches using SMTP. The `target` column must be a JSON object with fields like
  `{"smtp_server": "smtp.example.com", "smtp_port": 587, "use_tls": true, "sender": "samwatch@example.com", "recipients": ["alerts@example.com"]}`.

Ingestion commands now persist aggregated metrics (processed, created, updated, and attachment
statistics) in the `run_metrics` table, making it easier to audit historical sweeps and monitor
throughput trends.
