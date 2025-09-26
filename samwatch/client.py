"""HTTP client for interacting with the SAM.gov API."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from .config import Config
from .ratelimit import RateLimiter

logger = logging.getLogger(__name__)


class SAMClientError(RuntimeError):
    """Generic error raised when the SAM API returns an error response."""


@dataclass(slots=True)
class AttachmentDownload:
    """Metadata about a downloaded attachment."""

    url: str
    path: Path
    sha256: str
    bytes_written: int


class SAMWatchClient:
    """Lightweight wrapper over :mod:`httpx` tailored for the SAM.gov API."""

    def __init__(
        self,
        config: Config,
        *,
        rate_limiter: RateLimiter | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._config = config
        self._rate_limiter = rate_limiter or RateLimiter(
            hourly_limit=config.hourly_request_cap,
            daily_limit=config.daily_request_cap,
        )
        self._client = client or httpx.Client(
            timeout=config.http_timeout,
            headers={"X-Api-Key": config.api_key},
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def _perform_request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if not self._rate_limiter.acquire():
            raise SAMClientError("Unable to obtain rate limit token")

        url = path if path.startswith("http") else f"{self._config.base_url.rstrip('/')}/{path.lstrip('/')}"
        response = self._client.request(method, url, **kwargs)
        self._rate_limiter.update_from_headers(response.headers)
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            logger.warning("Received 429 from SAM.gov; sleeping for %s seconds", retry_after)
            self._rate_limiter.record_retry_after(retry_after)
            raise SAMClientError("Rate limited by SAM.gov API")
        if response.is_error:
            raise SAMClientError(
                f"SAM.gov API error: {response.status_code} {response.text[:200]}"
            )
        return response

    def search_opportunities(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Search for opportunities using the SAM.gov search endpoint."""

        query = dict(params)
        query.setdefault("limit", min(self._config.search_limit, 1000))
        response = self._perform_request("GET", "search", params=query)
        return response.json()

    def fetch_description(self, description_url: str) -> str:
        """Fetch detailed notice description text."""

        if "api_key=" not in description_url:
            separator = "&" if "?" in description_url else "?"
            description_url = f"{description_url}{separator}api_key={self._config.api_key}"
        response = self._perform_request("GET", description_url)
        return response.text

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, SAMClientError)),
        wait=wait_exponential_jitter(initial=1, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def download_attachment(self, url: str, destination: Path) -> AttachmentDownload:
        """Download an attachment and stream it to disk."""

        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._perform_request("GET", url, stream=True) as response:
            hash_ctx = hashlib.sha256()
            bytes_written = 0
            with destination.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
                    hash_ctx.update(chunk)
                    bytes_written += len(chunk)
        return AttachmentDownload(url=url, path=destination, sha256=hash_ctx.hexdigest(), bytes_written=bytes_written)

    def iter_search(self, params: Mapping[str, Any]) -> Iterable[dict[str, Any]]:
        """Iterate through paginated search results."""

        offset = int(params.get("offset", 0))
        limit = int(params.get("limit", min(self._config.search_limit, 1000)))
        while True:
            payload = dict(params, offset=offset, limit=limit)
            data = self.search_opportunities(payload)
            records = data.get("opportunitiesData", [])
            if not records:
                break
            for record in records:
                yield record
            offset += limit
            if offset >= data.get("totalRecords", 0):
                break
