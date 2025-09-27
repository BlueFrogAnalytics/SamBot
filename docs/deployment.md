# SAMWatch Deployment Playbook

This document outlines how to deploy and operate the SAMWatch service in a
production or staging environment. It focuses on reproducible configuration,
background execution, and ongoing maintenance.

## Prerequisites

- Python 3.11 or newer on the target host.
- Access to a persistent filesystem for the SQLite database and downloaded
  attachments.
- A valid SAM.gov API key exported as `SAM_API_KEY`.
- (Optional) SMTP credentials if email alerts will be used.

## Installation Steps

1. **Create an isolated environment**

   ```bash
   python -m venv /opt/samwatch/.venv
   source /opt/samwatch/.venv/bin/activate
   ```

2. **Fetch the code**

   ```bash
   git clone https://github.com/your-org/samwatch.git /opt/samwatch/app
   cd /opt/samwatch/app
   pip install -e .[dev]
   ```

3. **Bootstrap runtime directories**

   Ensure the data directories exist and have the correct permissions:

   ```bash
   mkdir -p /opt/samwatch/app/data/sqlite
   mkdir -p /opt/samwatch/app/data/files
   ```

4. **Configure environment variables**

   Create `/opt/samwatch/app/.env` with the following content and secure
   permissions (`chmod 600`):

   ```bash
   SAM_API_KEY="your-api-key"
   SAMWATCH_DATA_DIR="/opt/samwatch/app/data"
   SAMWATCH_SQLITE_PATH="/opt/samwatch/app/data/sqlite/samwatch.db"
   SAMWATCH_FILES_DIR="/opt/samwatch/app/data/files"
   SAMWATCH_ALERT_RETRY_ATTEMPTS="5"
   SAMWATCH_ALERT_RETRY_BACKOFF="3"
   ```

   Load the environment for interactive sessions with `set -a; source .env; set +a`.

## Running as a Service

Use `systemd` (or a similar init system) to keep the scheduler alive.

`/etc/systemd/system/samwatch.service`:

```
[Unit]
Description=SAMWatch ingestion service
After=network.target

[Service]
Type=simple
EnvironmentFile=/opt/samwatch/app/.env
WorkingDirectory=/opt/samwatch/app
ExecStart=/opt/samwatch/.venv/bin/samwatch serve
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now samwatch.service
```

## Scheduled Backfills

For periodic historical sweeps, schedule the CLI via `cron`:

```
0 3 * * 0 cd /opt/samwatch/app && \ 
  source /opt/samwatch/.venv/bin/activate && \ 
  samwatch run --warm && \ 
  samwatch run --cold --cold-start="2023-01-01" --cold-end="2023-01-31"
```

Adjust windows to avoid overlapping the main scheduler if rate limits are
constrained.

## Observability and Health

- The scheduler now tracks per-job metrics and emits a snapshot at DEBUG level
  during each health check. Enable verbose logging in the systemd unit by adding
  `Environment="LOG_LEVEL=DEBUG"` and configuring the Python logging
  configuration accordingly.
- Inspect recent ingestion runs:

  ```bash
  samwatch query "SELECT kind, started_at, status FROM runs ORDER BY started_at DESC LIMIT 10"
  ```

- Monitor disk utilisation in `data/files/` and plan pruning if required.

## Disaster Recovery

- Back up the SQLite database (`data/sqlite/samwatch.db`) on a regular cadence.
- Mirror the attachments directory or store attachments on durable network
  storage.
- Document how to rotate the SAM.gov API key and update the `.env` file.

## Automation Ideas

- Use Ansible or Terraform to provision the directory structure and systemd
  units.
- Integrate alert delivery endpoints (webhooks, email) with secrets managers to
  avoid storing credentials in plain text.
- Publish scheduler metrics to your central observability platform via a small
  sidecar script.
