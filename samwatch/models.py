"""Data models used across SAMWatch components."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(slots=True)
class Contact:
    name: str | None = None
    type: str | None = None
    email: str | None = None
    phone: str | None = None


@dataclass(slots=True)
class Attachment:
    url: str
    filename: str
    sha256: str | None = None
    bytes: int | None = None

    def destination_path(self, base_dir: Path, notice_id: str) -> Path:
        return base_dir / notice_id / self.filename


@dataclass(slots=True)
class Opportunity:
    notice_id: str
    title: str
    agency: str | None = None
    sub_tier: str | None = None
    office: str | None = None
    notice_type: str | None = None
    status: str | None = None
    posted_at: datetime | None = None
    updated_at: datetime | None = None
    response_deadline: datetime | None = None
    naics_codes: Iterable[str] | None = None
    set_aside: str | None = None
    digest: str | None = None
    contacts: list[Contact] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)


@dataclass(slots=True)
class Rule:
    name: str
    kind: str
    definition: str
    description: str | None = None
    is_active: bool = True


@dataclass(slots=True)
class AlertDestination:
    delivery_method: str
    target: str
