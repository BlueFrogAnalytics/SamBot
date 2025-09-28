# SAMWatch Build Tracker

## Mission
Implement the `samwatch` service described in the root plan to continuously monitor SAM.gov opportunities, persist rich records in SQLite, and surface alerts that match pursuit criteria.

## Current Goal
Stand up the initial project scaffolding (package layout, config plumbing, rate limiting utilities, and database schema) so functional development can begin immediately.

## Full Project Plan
1. **Scaffolding & Tooling**
   - Establish the `samwatch/` Python package with modules for configuration, rate limiting, API client, ingestion orchestrators, database helpers, alerting, and CLI entry points.
   - Create supporting directories: `data/sqlite/`, `data/files/`, and `docs/` (housing `sql_guide.md`).
   - Configure packaging (e.g., `pyproject.toml`) and basic linters/tests once scaffolding exists.

2. **Configuration & Secrets Management**
   - Implement `Config` dataclass that ingests `SAM_API_KEY`, frequency settings, and rate limit caps from environment variables and defaults.
   - Allow overrides via CLI flags or optional config file loader.

3. **Rate Limiting Infrastructure**
   - Build token bucket capable of tracking hourly and daily budgets.
   - Update budgets based on `X-RateLimit-*` headers and handle 429 responses with exponential backoff that respects `Retry-After`.

4. **SAM API Client**
   - Wrap search (`/opportunities/v2/search`), description fetch (noticedesc URL), and attachment downloads with resilient retries.
   - Support both `X-Api-Key` header and `?api_key=` query parameter fallbacks.

5. **Database Layer**
   - Define SQLite schema matching the mission tracker (opportunities, awards, contacts, descriptions, attachments, FTS5, rules, alerts, runs).
   - Supply migration/versioning helpers and reusable query utilities.

6. **Ingestion Pipelines**
   - **Hot Beam**: Rapid polling on today's window to catch new or edited notices.
   - **Warm Beam**: Scheduled rescans of the last 7 days to capture amendments and cancellations.
   - **Cold Sweep**: Background planner that backfills historical data month-by-month (≤ 1 year windows) until complete.
   - Detect record diffs via hashing, update `last_changed_at`, and enqueue downstream tasks.

7. **Workers & File Handling**
   - Fetch descriptions, clean text, and update the FTS virtual table.
   - Download attachments with checksum verification, retries, and metadata persistence.

8. **Alerting & Rules Engine**
   - Support JSON-defined pursuit criteria translated to SQL plus raw SQL rules.
   - Persist matches in `alerts` table and surface via email/webhook/CLI notifiers.

9. **Scheduler & CLI**
   - Provide commands: `samwatch run --hot`, `samwatch run --warm`, `samwatch backfill`, `samwatch query`, `samwatch status`.
   - Coordinate loop scheduling with rate limit availability and daily budget awareness.

10. **Documentation & Operations**
    - Maintain `docs/sql_guide.md` with canonical queries.
    - Document deployment, rate limit management, troubleshooting, and operational playbooks.

## Progress Checklist
- [x] Package skeleton created with placeholder modules.
- [x] Config dataclass implemented and tested against environment variables.
- [x] Rate limiter with hourly/daily accounting and header parsing.
- [x] SAM client capable of search, description, and attachment download.
- [x] SQLite schema defined and migrations runnable.
- [x] Ingestion loops operational (hot, warm, cold).
- [x] Alerting engine with rule evaluation and notification plumbing.
- [x] Documentation (SQL guide + ops) drafted and versioned.

## Next Action Steps
1. Export scheduler metrics to external observability tooling (Prometheus, OpenTelemetry).
2. Harden secret management for alert destinations (rotate credentials, support vault providers).

## Activity Log
- *2024-05-09*: Created `samwatch/AGENTS.md` to drive build execution within the `samwatch/` package scope.
- *2024-05-10*: Completed config, rate limiting, client, and database modules; added ingestion run tracking and outlined remaining alerting work.
- *2024-05-11*: Wired scheduler-driven CLI command with health checks for continuous ingestion.
- *2024-05-12*: Added templated alert delivery with retries, scheduler metrics, and deployment documentation.
- *2024-05-13*: Implemented end-to-end ingestion and alert integration tests to validate orchestration flows.
- *2024-05-14*: Updated ingestion, refresher, and scheduler codepaths to use timezone-aware timestamps for compatibility with modern Python.
