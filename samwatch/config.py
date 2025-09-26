"""Configuration loading utilities for SAMWatch."""

from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(RuntimeError):
    """Raised when the runtime configuration is invalid."""


@dataclass(slots=True)
class Config:
    """Runtime configuration for the SAMWatch service."""

    api_key: str
    data_dir: Path = field(default_factory=lambda: Path("data"))
    sqlite_path: Path = field(default_factory=lambda: Path("data/sqlite/samwatch.db"))
    files_dir: Path = field(default_factory=lambda: Path("data/files"))
    base_url: str = "https://api.sam.gov/opportunities/v2"
    search_limit: int = 100
    hourly_request_cap: int = 1000
    daily_request_cap: int | None = None
    http_timeout: float = 30.0
    hot_frequency_minutes: int = 15
    warm_frequency_minutes: int = 60
    cold_frequency_hours: int = 12

    @classmethod
    def from_env(
        cls, env: Mapping[str, str] | MutableMapping[str, str] | None = None, **overrides: object
    ) -> Config:
        """Create a :class:`Config` instance from environment variables."""

        env = env or os.environ
        api_key = str(overrides.pop("api_key", env.get("SAM_API_KEY", "")))
        if not api_key:
            raise ConfigError("SAM_API_KEY must be provided via environment or overrides")

        data_dir = Path(overrides.pop("data_dir", env.get("SAMWATCH_DATA_DIR", "data")))
        sqlite_path = Path(
            overrides.pop(
                "sqlite_path",
                env.get(
                    "SAMWATCH_SQLITE_PATH",
                    data_dir / "sqlite" / "samwatch.db",
                ),
            )
        )
        files_dir = Path(
            overrides.pop(
                "files_dir",
                env.get("SAMWATCH_FILES_DIR", data_dir / "files"),
            )
        )

        config = cls(
            api_key=api_key,
            data_dir=data_dir,
            sqlite_path=sqlite_path,
            files_dir=files_dir,
            base_url=str(
                overrides.pop("base_url", env.get("SAMWATCH_BASE_URL", cls.base_url))
            ),
            search_limit=int(
                overrides.pop("search_limit", env.get("SAMWATCH_SEARCH_LIMIT", cls.search_limit))
            ),
            hourly_request_cap=int(
                overrides.pop(
                    "hourly_request_cap",
                    env.get("SAMWATCH_HOURLY_CAP", cls.hourly_request_cap),
                )
            ),
            daily_request_cap=(
                int(daily_cap)
                if (daily_cap := overrides.pop(
                    "daily_request_cap", env.get("SAMWATCH_DAILY_CAP", "")
                ))
                else cls.daily_request_cap
            ),
            http_timeout=float(
                overrides.pop(
                    "http_timeout", env.get("SAMWATCH_HTTP_TIMEOUT", cls.http_timeout)
                )
            ),
            hot_frequency_minutes=int(
                overrides.pop(
                    "hot_frequency_minutes",
                    env.get("SAMWATCH_HOT_FREQUENCY", cls.hot_frequency_minutes),
                )
            ),
            warm_frequency_minutes=int(
                overrides.pop(
                    "warm_frequency_minutes",
                    env.get("SAMWATCH_WARM_FREQUENCY", cls.warm_frequency_minutes),
                )
            ),
            cold_frequency_hours=int(
                overrides.pop(
                    "cold_frequency_hours",
                    env.get("SAMWATCH_COLD_FREQUENCY", cls.cold_frequency_hours),
                )
            ),
        )

        if overrides:
            unexpected = ", ".join(sorted(overrides))
            raise ConfigError(f"Unexpected configuration overrides: {unexpected}")

        config.ensure_directories()
        return config

    def ensure_directories(self) -> None:
        """Ensure that filesystem paths required by the service exist."""

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.files_dir.mkdir(parents=True, exist_ok=True)

    def as_dict(self) -> dict[str, object]:
        """Serialize configuration to a mapping for debugging or logging."""

        return {
            "base_url": self.base_url,
            "data_dir": str(self.data_dir),
            "sqlite_path": str(self.sqlite_path),
            "files_dir": str(self.files_dir),
            "search_limit": self.search_limit,
            "hourly_request_cap": self.hourly_request_cap,
            "daily_request_cap": self.daily_request_cap,
            "http_timeout": self.http_timeout,
            "hot_frequency_minutes": self.hot_frequency_minutes,
            "warm_frequency_minutes": self.warm_frequency_minutes,
            "cold_frequency_hours": self.cold_frequency_hours,
        }
