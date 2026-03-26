"""HTTP fetching utilities for crawler pipeline."""

from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(slots=True)
class FetchResult:
    """Represent a successful HTTP fetch response."""

    url: str
    status_code: int
    text: str


class Fetcher:
    """Thin wrapper around an HTTPX client used by the crawler."""

    def __init__(self, *, user_agent: str, timeout_seconds: float) -> None:
        """Create an HTTP client configured for crawler requests."""
        self.client = httpx.Client(
            headers={"User-Agent": user_agent},
            follow_redirects=True,
            timeout=timeout_seconds,
        )

    def fetch(self, url: str) -> FetchResult:
        """Fetch one URL and raise on non-success status codes."""
        response = self.client.get(url)
        response.raise_for_status()
        return FetchResult(url=str(response.url), status_code=response.status_code, text=response.text)
