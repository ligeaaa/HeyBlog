"""HTTPX-backed crawler fetching strategy."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from crawler.crawling.fetching.base import FetchAttempt
from crawler.crawling.fetching.base import FetchResult


class Fetcher:
    """Thin wrapper around an HTTPX client used by the crawler."""

    def __init__(self, *, user_agent: str, timeout_seconds: float) -> None:
        self._client_kwargs: dict[str, Any] = {
            "headers": {"User-Agent": user_agent},
            "follow_redirects": True,
            "timeout": timeout_seconds,
        }
        self.client = httpx.Client(**self._client_kwargs)

    def fetch(self, url: str, *, timeout_seconds: float | None = None) -> FetchResult:
        """Fetch one URL and raise on non-success status codes."""
        request_kwargs: dict[str, Any] = {}
        if timeout_seconds is not None:
            request_kwargs["timeout"] = timeout_seconds
        response = self.client.get(url, **request_kwargs)
        response.raise_for_status()
        return FetchResult(url=str(response.url), status_code=response.status_code, text=response.text)

    def fetch_many(
        self,
        urls: list[str],
        *,
        max_concurrency: int,
        timeout_seconds: float | None = None,
    ) -> dict[str, FetchAttempt]:
        """Fetch a batch of URLs while preserving the original request key space."""
        self._validate_fetch_many_inputs(urls, max_concurrency=max_concurrency)
        if not urls:
            return {}
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.fetch_many_async(
                    urls,
                    max_concurrency=max_concurrency,
                    timeout_seconds=timeout_seconds,
                )
            )
        raise RuntimeError(
            "Fetcher.fetch_many() cannot be called from a running asyncio event loop. "
            "Use 'await fetch_many_async(...)' instead."
        )

    async def fetch_many_async(
        self,
        urls: list[str],
        *,
        max_concurrency: int,
        timeout_seconds: float | None = None,
    ) -> dict[str, FetchAttempt]:
        """Async batch-fetch entrypoint for callers already in an event loop."""
        self._validate_fetch_many_inputs(urls, max_concurrency=max_concurrency)
        if not urls:
            return {}
        return await self._fetch_many_async(
            urls,
            max_concurrency=max_concurrency,
            timeout_seconds=timeout_seconds,
        )

    async def _fetch_many_async(
        self,
        urls: list[str],
        *,
        max_concurrency: int,
        timeout_seconds: float | None = None,
    ) -> dict[str, FetchAttempt]:
        """Fetch multiple URLs concurrently with the same HTTP contract as fetch()."""
        semaphore = asyncio.Semaphore(max_concurrency)

        async def fetch_one(client: httpx.AsyncClient, request_url: str) -> tuple[str, FetchAttempt]:
            async with semaphore:
                try:
                    request_kwargs: dict[str, Any] = {}
                    if timeout_seconds is not None:
                        request_kwargs["timeout"] = timeout_seconds
                    response = await client.get(request_url, **request_kwargs)
                    response.raise_for_status()
                except httpx.InvalidURL:
                    return (request_url, FetchAttempt(request_url=request_url, result=None, error_kind="invalid_url"))
                except httpx.TimeoutException:
                    return (request_url, FetchAttempt(request_url=request_url, result=None, error_kind="timeout"))
                except httpx.HTTPStatusError:
                    return (request_url, FetchAttempt(request_url=request_url, result=None, error_kind="http_status"))
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

    def _validate_fetch_many_inputs(self, urls: list[str], *, max_concurrency: int) -> None:
        """Validate public batch-fetch inputs before any network work starts."""
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        if len(urls) != len(set(urls)):
            raise ValueError("fetch_many() requires unique request URLs")
