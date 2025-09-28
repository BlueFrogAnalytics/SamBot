# SAMWatch Mission Tracker

## Goal
Build a Python service (`samwatch/`) that continuously scans SAM.gov opportunities, captures descriptions and attachments, persists them in SQLite with FTS, and drives alerting based on pursuit rules while operating within SAM.gov API rate limits.

## Constraints & Reality Checks
- **API Endpoint**: `https://api.sam.gov/opportunities/v2/search` (requires `postedFrom`, `postedTo`, `limit ≤ 1000`, offset pagination, ≤ 1 year window).
- **Authentication**: Supply API key via `X-Api-Key` header; some description/resource links may require `?api_key=` fallback.
- **Rate Limits**: Defaults of 1,000 requests/hour (`X-RateLimit-*` headers). Daily caps vary by key type (e.g., 10/1,000/10,000 per docs). Must handle 429 + `Retry-After` with backoff.
- **Responses**: Include `resourceLinks` (attachments) and `description` URL needing separate fetch with API key appended if necessary.
- **Opportunity Types**: Filter via `ptype` (u, p, a, r, s, o, g, k, i) as needed.
- **Storage**: SQLite DB + FTS5 for search; attachments stored on disk under `data/files/<noticeId>/`.

## Project Plan
1. **Repository Scaffolding**
   - Create `samwatch/` package with modules: `config.py`, `ratelimit.py`, `client.py`, `ingest.py`, `backfill.py`, `refresher.py`, `alerts.py`, `models.py`, `db.py`, `scheduler.py`, `cli.py`.
   - Establish data directories (`data/sqlite/`, `data/files/`) and docs (`docs/sql_guide.md`).
2. **Configuration & Secrets**
   - Implement dataclass-based config loader that reads env vars (`SAM_API_KEY`) and runtime parameters (frequencies, caps, directories).
   - Support overrides via CLI flags / config file as future enhancement.
3. **Rate Limiting**
   - Token bucket handling hourly + daily caps; parse `X-RateLimit-*` headers to adjust budgets dynamically.
   - Implement exponential backoff with jitter honoring `Retry-After` on 429.
4. **SAM Client**
   - Wrap search, description fetch, and attachment downloads with robust error handling and auth fallbacks.
   - Stream downloads to disk, compute SHA256, store metadata.
5. **Data Layer**
   - Define SQLite schema per specification (opportunities, awards, contacts, descriptions, attachments, FTS, rules, alerts, runs).
   - Provide migration helpers and query utilities; include SQL guide examples in `docs/sql_guide.md`.
6. **Ingestion Pipelines**
   - **Hot Beam**: Frequent scans (`postedFrom=postedTo=today`) with overlap to catch new notices quickly.
   - **Warm Beam**: Periodic rescans of last 7 days to detect amendments/archivals, updating `last_changed_at` on diffs.
   - **Cold Sweep**: Background backfill planning monthly/quarterly windows until history complete; persist progress in DB.
7. **Workers & Processing**
   - Fetch descriptions, update FTS index, and download attachments asynchronously with retries and checksum verification.
   - Update DB tables atomically (upserts) and track run statistics.
8. **Alerting Engine**
   - Support JSON criteria → SQL translation and direct SQL rules.
   - Deliver notifications via email/webhook/CLI; log matches in `alerts` table.
9. **CLI & Scheduler**
   - Provide commands: `samwatch run --hot`, `samwatch run --warm`, `samwatch backfill`, `samwatch query`, `samwatch status`.
   - Integrate scheduler (APScheduler or custom) respecting rate limiter budgets.
10. **Documentation & Ops**
    - Maintain `docs/sql_guide.md` with queries (new in 24h, pursuit filters, FTS search, agency counts, attachment counts).
    - Document rate limit management, API usage, ops playbook, and environment setup.

## Progress Checklist
- [x] Repository scaffolding in place (`samwatch/` app modules, CLI entry point).
- [x] Configuration and rate limiting utilities implemented.
- [x] SAM.gov client for search, descriptions, and attachment downloads.
- [x] SQLite schema and migration helpers created.
- [x] Ingestion pipeline (hot, warm, cold beams) running with persistence.
- [x] Alerting engine with rules and notifications.
- [x] Documentation (SQL guide, ops playbook) written and up to date.

## Activity Log
- *2024-05-05*: Initialized mission tracker file.
- *2024-05-09*: Expanded tracker with full project plan, constraints, and phased roadmap.
- *2024-05-10*: Implemented scaffolding, configuration, rate limiting, client, and database layers; added run tracking for ingestion sweeps.
- *2024-05-11*: Added scheduler-driven CLI orchestration with periodic health checks.
- *2024-05-12*: Delivered alert templating with retries, scheduler metrics, and deployment documentation.
- *2024-05-13*: Added integration coverage for ingestion hot sweeps and alert rule evaluation.

## Working Agreements
- Keep SAM API keys out of source control (load from environment `SAM_API_KEY`).
- Respect documented rate limits; throttle proactively before hitting hard caps.
- Update this tracker whenever milestones complete or priorities shift.
