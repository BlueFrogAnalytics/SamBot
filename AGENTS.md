# SAMWatch Mission Tracker

## Goal
Build a Python service (`samwatch/`) that continuously scans SAM.gov opportunities, captures descriptions and attachments, persists them in SQLite with FTS, and drives alerting based on pursuit rules while operating within SAM.gov API rate limits.

## Current Status
- [ ] Repository scaffolding in place (`samwatch/` app modules, CLI entry point).
- [ ] Configuration and rate limiting utilities implemented.
- [ ] SAM.gov client for search, descriptions, and attachment downloads.
- [ ] SQLite schema and migration helpers created.
- [ ] Ingestion pipeline (hot, warm, cold beams) running with persistence.
- [ ] Alerting engine with rules and notifications.
- [ ] Documentation (SQL guide, ops playbook) written and up to date.

## Next Steps
1. Scaffold Python package layout and baseline dependencies.
2. Implement configuration handling and secure API key loading.
3. Build rate limiter honoring hourly/daily caps and Retry-After headers.
4. Develop SAM API client covering search, description fetch, and attachment download flows.
5. Design SQLite schema (opportunities, awards, contacts, descriptions, attachments, FTS, alerts, runs) and migrations.
6. Implement ingestion loops (hot, warm, cold) with resume capability.
7. Wire attachment/description workers with retry + checksum handling.
8. Create alert rule engine and notification outputs (email/webhook/CLI).
9. Add CLI commands (`samwatch run`, `samwatch backfill`, `samwatch query`) and docs (`docs/sql_guide.md`).

## Activity Log
- *2024-05-05*: Initialized mission tracker file.

## Working Agreements
- Keep SAM API keys out of source control (load from environment `SAM_API_KEY`).
- Respect documented rate limits; throttle proactively before hitting hard caps.
- Update this tracker whenever milestones complete or priorities shift.
