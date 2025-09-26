"""Alert evaluation engine for SAMWatch."""

from __future__ import annotations

import json
import logging
from typing import Iterable, Mapping

from .db import Database

logger = logging.getLogger(__name__)


class AlertEngine:
    """Evaluate pursuit rules against the database and persist matches."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def evaluate_rules(self) -> None:
        """Run all active rules and persist their matches."""

        with self.database.cursor() as cur:
            cur.execute("SELECT id, kind, definition FROM rules WHERE is_active = 1")
            rules = cur.fetchall()

        for rule in rules:
            kind = rule[1]
            definition = rule[2]
            try:
                if kind == "sql":
                    matches = self._execute_sql(definition)
                elif kind == "json":
                    matches = self._execute_json_rule(definition)
                else:
                    logger.warning("Unknown rule kind %s", kind)
                    continue
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Failed to evaluate rule %s: %s", rule[0], exc)
                continue

            self._persist_matches(rule[0], matches)

    def _execute_sql(self, statement: str) -> Iterable[Mapping[str, object]]:
        cur = self.database.execute(statement)
        columns = [col[0] for col in cur.description]
        rows = cur.fetchall()
        return [dict(zip(columns, row)) for row in rows]

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
        return [dict(zip(row.keys(), row)) for row in rows]

    def _persist_matches(self, rule_id: int, matches: Iterable[Mapping[str, object]]) -> None:
        with self.database.cursor() as cur:
            for match in matches:
                opportunity_id = match.get("opportunity_id")
                if opportunity_id is None:
                    continue
                cur.execute(
                    """
                    INSERT INTO rule_matches (rule_id, opportunity_id)
                    VALUES (?, ?)
                    ON CONFLICT(rule_id, opportunity_id) DO UPDATE SET matched_at = CURRENT_TIMESTAMP
                    """,
                    (rule_id, opportunity_id),
                )
