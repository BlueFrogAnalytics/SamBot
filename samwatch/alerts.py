"""Alert evaluation routines for SAMWatch."""

from __future__ import annotations

import json
import logging
import smtplib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any

import httpx
from rich.console import Console
from rich.table import Table

from .config import Config
from .db import Database

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AlertDestination:
    """Configuration for delivering notifications."""

    id: int
    method: str
    target: str


@dataclass(slots=True)
class MatchRecord:
    """Representation of an opportunity that matched a rule."""

    opportunity_id: int
    payload: Mapping[str, Any] | None = None


class AlertEngine:
    """Evaluate pursuit rules against the database and persist matches."""

    def __init__(self, config: Config, database: Database) -> None:
        self.config = config
        self.database = database
        self._console = Console()

    def evaluate_rules(self) -> None:
        """Run all active rules and persist their matches."""

        with self.database.cursor() as cur:
            cur.execute(
                "SELECT id, name, kind, definition FROM rules WHERE is_active = 1"
            )
            rules = cur.fetchall()

        for rule in rules:
            rule_id = rule[0]
            rule_name = rule[1]
            kind = rule[2]
            definition = rule[3]
            try:
                if kind == "sql":
                    matches = self._execute_sql(definition)
                elif kind == "json":
                    matches = self._execute_json_rule(definition)
                else:
                    logger.warning("Unknown rule kind %s", kind)
                    continue
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Failed to evaluate rule %s: %s", rule_id, exc)
                continue

            new_matches = self._persist_matches(rule_id, matches)
            if not new_matches:
                logger.debug("Rule %s produced no new matches", rule_name)
                continue

            logger.info(
                "Rule %s produced %d new matches", rule_name, len(new_matches)
            )
            self._dispatch_notifications(rule_id, rule_name, new_matches)

    def _execute_sql(self, statement: str) -> Iterable[Mapping[str, object]]:
        cur = self.database.execute(statement)
        rows = cur.fetchall()
        return [dict(row) for row in rows]

    def _execute_json_rule(self, definition: str) -> Iterable[Mapping[str, object]]:
        payload = json.loads(definition)
        terms = payload.get("terms", [])
        sql = "SELECT id AS opportunity_id FROM opportunities WHERE 1=1"
        parameters: list[object] = []
        for term in terms:
            field = term.get("field")
            value = term.get("value")
            if not field or value is None:
                continue
            sql += f" AND {field} LIKE ?"
            parameters.append(f"%{value}%")
        cur = self.database.execute(sql, parameters)
        rows = cur.fetchall()
        return [dict(row) for row in rows]

    def _persist_matches(
        self, rule_id: int, matches: Iterable[Mapping[str, object]]
    ) -> list[MatchRecord]:
        new_matches: list[MatchRecord] = []
        with self.database.cursor() as cur:
            for match in matches:
                if not isinstance(match, Mapping):
                    continue
                opportunity_id = match.get("opportunity_id")
                if opportunity_id is None:
                    continue
                try:
                    opportunity_id_int = int(opportunity_id)
                except (TypeError, ValueError):
                    logger.debug(
                        "Skipping match with non-integer opportunity_id: %s",
                        opportunity_id,
                    )
                    continue
                payload = {
                    key: value
                    for key, value in match.items()
                    if key != "opportunity_id"
                }
                payload_json = json.dumps(payload, default=str) if payload else None
                cur.execute(
                    "SELECT 1 FROM rule_matches WHERE rule_id = ? AND opportunity_id = ?",
                    (rule_id, opportunity_id_int),
                )
                existed = cur.fetchone() is not None
                cur.execute(
                    """
                    INSERT INTO rule_matches (rule_id, opportunity_id, payload)
                    VALUES (?, ?, ?)
                    ON CONFLICT(rule_id, opportunity_id) DO UPDATE
                        SET matched_at = CURRENT_TIMESTAMP,
                            payload = COALESCE(excluded.payload, payload)
                    """,
                    (rule_id, opportunity_id_int, payload_json),
                )
                if not existed:
                    new_matches.append(MatchRecord(opportunity_id_int, payload or None))
        return new_matches

    def _dispatch_notifications(
        self, rule_id: int, rule_name: str, matches: Sequence[MatchRecord]
    ) -> None:
        if not matches:
            return
        destinations = self._load_destinations(rule_id)
        if not destinations:
            logger.info("No alert destinations configured for rule %s", rule_name)
            return

        summaries = self._load_opportunity_summaries(
            [match.opportunity_id for match in matches]
        )
        entries: list[dict[str, Any]] = []
        for match in matches:
            summary = summaries.get(match.opportunity_id, {})
            notice_id = summary.get("notice_id")
            entries.append(
                {
                    "opportunity_id": match.opportunity_id,
                    "notice_id": notice_id,
                    "title": summary.get("title"),
                    "agency": summary.get("agency"),
                    "posted_at": summary.get("posted_at"),
                    "url": self._build_notice_url(notice_id) if notice_id else None,
                    "payload": dict(match.payload) if match.payload else {},
                }
            )

        normalized_entries = self._normalize_entries(entries)

        for destination in destinations:
            try:
                self._send_notification(destination, rule_name, normalized_entries)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception(
                    "Failed to deliver alert %s via %s: %s",
                    destination.id,
                    destination.method,
                    exc,
                )

    def _load_destinations(self, rule_id: int) -> list[AlertDestination]:
        cursor = self.database.execute(
            "SELECT id, delivery_method, target FROM alerts WHERE rule_id = ?",
            (rule_id,),
        )
        rows = cursor.fetchall()
        return [
            AlertDestination(
                id=row["id"],
                method=str(row["delivery_method"]),
                target=str(row["target"]),
            )
            for row in rows
        ]

    def _load_opportunity_summaries(
        self, opportunity_ids: Sequence[int]
    ) -> dict[int, dict[str, Any]]:
        if not opportunity_ids:
            return {}
        unique_ids = list(dict.fromkeys(opportunity_ids))
        placeholders = ",".join("?" for _ in unique_ids)
        cursor = self.database.execute(
            f"""
            SELECT id, notice_id, title, agency, posted_at
            FROM opportunities
            WHERE id IN ({placeholders})
            """,
            unique_ids,
        )
        return {row["id"]: dict(row) for row in cursor.fetchall()}

    def _build_notice_url(self, notice_id: str | None) -> str | None:
        if not notice_id:
            return None
        return f"https://sam.gov/opp/{notice_id}/view"

    def _send_notification(
        self, destination: AlertDestination, rule_name: str, entries: Sequence[dict[str, Any]]
    ) -> None:
        method = destination.method.lower()
        if method in {"cli", "console"}:
            self._send_cli_notification(rule_name, entries)
        elif method == "webhook":
            self._send_webhook_notification(destination.target, rule_name, entries)
        elif method == "email":
            self._send_email_notification(destination.target, rule_name, entries)
        else:
            logger.warning("Unsupported alert delivery method %s", destination.method)

    def _send_cli_notification(
        self, rule_name: str, entries: Sequence[dict[str, Any]]
    ) -> None:
        table = Table(title=f"Alert matches for rule: {rule_name}")
        table.add_column("Notice ID")
        table.add_column("Title")
        table.add_column("Agency")
        table.add_column("URL")
        for entry in entries:
            table.add_row(
                entry.get("notice_id") or "-",
                entry.get("title") or "-",
                entry.get("agency") or "-",
                entry.get("url") or "-",
            )
        self._console.print(table)

    def _send_webhook_notification(
        self, target: str, rule_name: str, entries: Sequence[dict[str, Any]]
    ) -> None:
        parsed_target = self._parse_target(target)
        headers: dict[str, str] | None = None
        url: str | None = None
        if isinstance(parsed_target, Mapping):
            url = str(parsed_target.get("url")) if parsed_target.get("url") else None
            headers_obj = parsed_target.get("headers") or {}
            if isinstance(headers_obj, Mapping):
                headers = {str(k): str(v) for k, v in headers_obj.items()}
        elif isinstance(parsed_target, str):
            url = parsed_target
        if not url:
            logger.warning("Webhook target missing URL: %s", target)
            return
        payload = {"rule": rule_name, "matches": entries}
        httpx.post(url, json=payload, headers=headers, timeout=self.config.http_timeout)

    def _send_email_notification(
        self, target: str, rule_name: str, entries: Sequence[dict[str, Any]]
    ) -> None:
        settings = self._parse_target(target)
        if not isinstance(settings, Mapping):
            logger.warning("Email alert target must be a JSON object: %s", target)
            return

        smtp_server = settings.get("smtp_server")
        sender = settings.get("sender")
        recipients = settings.get("recipients")
        if not smtp_server or not sender or not recipients:
            logger.warning("Email alert target missing required fields: %s", target)
            return

        if isinstance(recipients, str):
            recipient_list = [recipients]
        else:
            recipient_list = [str(r) for r in recipients]

        subject = settings.get("subject") or f"SAMWatch matches for {rule_name}"
        body_lines = [f"Matches for rule {rule_name}:", ""]
        for entry in entries:
            body_lines.append(
                f"- {entry.get('notice_id') or entry.get('opportunity_id')}: {entry.get('title') or 'Untitled'}"
            )
            if entry.get("url"):
                body_lines.append(f"  URL: {entry['url']}")
            if entry.get("agency"):
                body_lines.append(f"  Agency: {entry['agency']}")
            if entry.get("payload"):
                body_lines.append("  Payload:")
                body_lines.append(json.dumps(entry["payload"], indent=2, default=str))
            body_lines.append("")

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = str(sender)
        message["To"] = ", ".join(recipient_list)
        message.set_content("\n".join(body_lines))

        port = int(settings.get("smtp_port", 25))
        username = settings.get("username")
        password = settings.get("password")
        use_tls = bool(settings.get("use_tls", False))

        with smtplib.SMTP(str(smtp_server), port, timeout=self.config.http_timeout) as smtp:
            if use_tls:
                smtp.starttls()
            if username and password:
                smtp.login(str(username), str(password))
            smtp.send_message(message)

    def _parse_target(self, target: str) -> Any:
        try:
            return json.loads(target)
        except json.JSONDecodeError:
            return target

    def _normalize_entries(
        self, entries: Sequence[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return [
            {
                **entry,
                "payload": self._normalize_payload(entry.get("payload", {})),
            }
            for entry in entries
        ]

    def _normalize_payload(self, payload: Any) -> Any:
        if isinstance(payload, Mapping):
            return {k: self._normalize_payload(v) for k, v in payload.items()}
        if isinstance(payload, list):
            return [self._normalize_payload(item) for item in payload]
        if isinstance(payload, (str, int, float, bool)) or payload is None:
            return payload
        return str(payload)
