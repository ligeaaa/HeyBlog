"""HTTP fetching utilities for crawler pipeline."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(slots=True)
class FetchResult:
    """Represent a successful HTTP fetch response."""

    url: str
    status_code: int
    text: str


@dataclass(slots=True)
class FetchAttempt:
    """Represent one batch fetch outcome keyed by the original request URL."""

    request_url: str
    result: FetchResult | None
    error_kind: str | None


class Fetcher:
    """Thin wrapper around an HTTPX client used by the crawler."""

    def __init__(self, *, user_agent: str, timeout_seconds: float) -> None:
        """Create an HTTP client configured for crawler requests."""
        self._client_kwargs: dict[str, Any] = {
            "headers": {"User-Agent": user_agent},
            "follow_redirects": True,
            "timeout": timeout_seconds,
        }
        self.client = httpx.Client(**self._client_kwargs)

    def fetch(self, url: str) -> FetchResult:
        """Fetch one URL and raise on non-success status codes."""
        response = self.client.get(url)
        response.raise_for_status()
        return FetchResult(url=str(response.url), status_code=response.status_code, text=response.text)

    def fetch_many(self, urls: list[str], *, max_concurrency: int) -> dict[str, FetchAttempt]:
        """Fetch a batch of URLs while preserving the original request key space."""
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        if not urls:
            return {}
        return asyncio.run(self._fetch_many_async(urls, max_concurrency=max_concurrency))

    async def _fetch_many_async(
        self,
        urls: list[str],
        *,
        max_concurrency: int,
    ) -> dict[str, FetchAttempt]:
        """Fetch multiple URLs concurrently with the same HTTP contract as fetch()."""
        semaphore = asyncio.Semaphore(max_concurrency)

        async def fetch_one(
            client: httpx.AsyncClient,
            request_url: str,
        ) -> tuple[str, FetchAttempt]:
            async with semaphore:
                try:
                    response = await client.get(request_url)
                    response.raise_for_status()
                except httpx.TimeoutException:
                    return (
                        request_url,
                        FetchAttempt(request_url=request_url, result=None, error_kind="timeout"),
                    )
                except httpx.HTTPStatusError:
                    return (
                        request_url,
                        FetchAttempt(request_url=request_url, result=None, error_kind="http_status"),
                    )
                except httpx.RequestError:
                    return (
                        request_url,
                        FetchAttempt(request_url=request_url, result=None, error_kind="request_error"),
                    )

                return (
                    request_url,
                    FetchAttempt(
                        request_url=request_url,
                        result=FetchResult(
                            url=str(response.url),
                            status_code=response.status_code,
                            text=response.text,
                        ),
                        error_kind=None,
                    ),
                )

        async with httpx.AsyncClient(**self._client_kwargs) as client:
            attempts = await asyncio.gather(*(fetch_one(client, request_url) for request_url in urls))
        return dict(attempts)
