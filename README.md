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
- Typer-based command line interface for running ingestion pipelines and queries
- Run tracking persisted in the SQLite `runs` table for observability

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

## Development

- Configure formatting and linting with `ruff` using the settings in `pyproject.toml`.
- Tests can be added under `tests/` and run with `pytest`.
- See `docs/sql_guide.md` for example analytical queries against the SQLite database.

## Roadmap

This repository currently includes the foundational scaffolding for SAMWatch. Upcoming work
includes implementing full ingestion pipelines, attachment handling, alert delivery
integrations, and operational documentation.
