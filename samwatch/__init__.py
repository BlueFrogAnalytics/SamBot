"""Top-level package for the SAMWatch service."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("samwatch")
except PackageNotFoundError:  # pragma: no cover - best effort during development
    __version__ = "0.0.0"

__all__ = ["__version__"]
