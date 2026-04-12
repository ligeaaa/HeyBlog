"""HTTPX-backed crawler fetching strategy."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from crawler.crawling.fetching.base import FetchAttempt
from crawler.crawling.fetching.base import FetchResult
from crawler.crawling.fetching.base import PageTooLargeError


class Fetcher:
    """Fetch crawler pages over HTTPX with size limits and batch support.

    The fetcher centralizes request headers, timeout handling, response size
    enforcement, and batch concurrency so the rest of the crawler can treat
    HTTP retrieval as one stable abstraction.
    """

    def __init__(self, *, user_agent: str, timeout_seconds: float, max_page_bytes: int) -> None:
        """Initialize one fetcher with shared HTTP client configuration.

        Args:
            user_agent: User-Agent header sent on all crawler requests.
            timeout_seconds: Default timeout, in seconds, for requests that do
                not provide a more specific override.
            max_page_bytes: Maximum response body size accepted before failing
                the fetch as too large.

        Returns:
            None. The method stores a ready-to-use sync HTTPX client and shared
            fetch limits on the instance.
        """
        self._client_kwargs: dict[str, Any] = {
            "headers": {"User-Agent": user_agent},
            "follow_redirects": True,
            "timeout": timeout_seconds,
        }
        self.client = httpx.Client(**self._client_kwargs)
        self.max_page_bytes = max(1, int(max_page_bytes))

    def fetch(self, url: str, *, timeout_seconds: float | None = None) -> FetchResult:
        """Fetch one URL synchronously for the crawler.

        Args:
            url: Absolute URL to request.
            timeout_seconds: Optional timeout override for this request only.

        Returns:
            A ``FetchResult`` containing the final URL, status code, and decoded
            response body.
        """
        request_kwargs: dict[str, Any] = {}
        if timeout_seconds is not None:
            request_kwargs["timeout"] = timeout_seconds
        with self.client.stream("GET", url, **request_kwargs) as response:
            response.raise_for_status()
            text = self._read_response_text(response)
            return FetchResult(url=str(response.url), status_code=response.status_code, text=text)

    def fetch_many(
        self,
        urls: list[str],
        *,
        max_concurrency: int,
        timeout_seconds: float | None = None,
    ) -> dict[str, FetchAttempt]:
        """Fetch a batch of URLs from synchronous crawler code.

        Args:
            urls: Absolute URLs to retrieve.
            max_concurrency: Maximum concurrent requests allowed in the batch.
            timeout_seconds: Optional timeout override for each request.

        Returns:
            A mapping from each original request URL to a ``FetchAttempt``
            describing success or classified failure.
        """
        self._validate_fetch_many_inputs(urls, max_concurrency=max_concurrency)
        if not urls:
            return {}
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # The sync crawler path delegates to the async batch implementation
            # so candidate pages can still be fetched concurrently in one-shot runs.
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
        """Fetch a batch of URLs from async callers already in an event loop.

        Args:
            urls: Absolute URLs to retrieve.
            max_concurrency: Maximum number of simultaneous requests.
            timeout_seconds: Optional timeout override for each request.

        Returns:
            A mapping from each original request URL to a ``FetchAttempt``.
        """
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
        """Fetch multiple URLs concurrently with the same contract as ``fetch``.

        Args:
            urls: Absolute URLs to retrieve.
            max_concurrency: Maximum concurrent requests allowed for the batch.
            timeout_seconds: Optional timeout override for each request.

        Returns:
            A mapping from original request URLs to ``FetchAttempt`` results.
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def fetch_one(client: httpx.AsyncClient, request_url: str) -> tuple[str, FetchAttempt]:
            """Fetch one URL inside the shared async batch execution.

            Args:
                client: Shared async HTTPX client used for the batch.
                request_url: Original URL for this individual request.

            Returns:
                A tuple of ``(request_url, FetchAttempt)`` so the outer batch can
                rebuild a mapping keyed by discovery order rather than response
                order.
            """
            async with semaphore:
                try:
                    request_kwargs: dict[str, Any] = {}
                    if timeout_seconds is not None:
                        request_kwargs["timeout"] = timeout_seconds
                    async with client.stream("GET", request_url, **request_kwargs) as response:
                        response.raise_for_status()
                        text = await self._read_response_text_async(response)
                except httpx.InvalidURL:
                    return (request_url, FetchAttempt(request_url=request_url, result=None, error_kind="invalid_url"))
                except httpx.TimeoutException:
                    return (request_url, FetchAttempt(request_url=request_url, result=None, error_kind="timeout"))
                except httpx.HTTPStatusError:
                    return (request_url, FetchAttempt(request_url=request_url, result=None, error_kind="http_status"))
                except PageTooLargeError:
                    return (
                        request_url,
                        FetchAttempt(request_url=request_url, result=None, error_kind="page_too_large"),
                    )
                except httpx.RequestError:
                    return (
                        request_url,
                        FetchAttempt(request_url=request_url, result=None, error_kind="request_error"),
                    )

                # Key each attempt by the original request URL so callers can map
                # results back onto their own discovery order after redirects.
                return (
                    request_url,
                    FetchAttempt(
                        request_url=request_url,
                        result=FetchResult(
                            url=str(response.url),
                            status_code=response.status_code,
                            text=text,
                        ),
                        error_kind=None,
                    ),
                )

        async with httpx.AsyncClient(**self._client_kwargs) as client:
            attempts = await asyncio.gather(*(fetch_one(client, request_url) for request_url in urls))
        return dict(attempts)

    def _validate_fetch_many_inputs(self, urls: list[str], *, max_concurrency: int) -> None:
        """Validate batch-fetch inputs before any network work starts.

        Args:
            urls: Original request URLs supplied by the caller.
            max_concurrency: Requested maximum concurrency for the batch.

        Returns:
            None. Invalid inputs raise ``ValueError`` before any requests are
            attempted.
        """
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        if len(urls) != len(set(urls)):
            raise ValueError("fetch_many() requires unique request URLs")

    def _read_response_text(self, response: httpx.Response) -> str:
        """Decode one synchronous HTTP response body into text.

        Args:
            response: Streaming HTTPX response to decode.

        Returns:
            The decoded response body text, using the response encoding when
            available and replacing undecodable bytes.
        """
        content = self._collect_response_bytes(response)
        encoding = response.encoding or "utf-8"
        return content.decode(encoding, errors="replace")

    async def _read_response_text_async(self, response: httpx.Response) -> str:
        """Decode one asynchronous HTTP response body into text.

        Args:
            response: Streaming async HTTPX response to decode.

        Returns:
            The decoded response body text, using the response encoding when
            available and replacing undecodable bytes.
        """
        content = await self._collect_response_bytes_async(response)
        encoding = response.encoding or "utf-8"
        return content.decode(encoding, errors="replace")

    def _collect_response_bytes(self, response: httpx.Response) -> bytes:
        """Collect a synchronous response body while enforcing size limits.

        Args:
            response: Streaming HTTPX response whose bytes should be consumed.

        Returns:
            The full response body as bytes when it fits within the configured
            size cap.
        """
        self._raise_if_content_length_too_large(response)
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > self.max_page_bytes:
                # Enforce the size cap while streaming so unexpectedly large
                # pages fail fast instead of being buffered into memory first.
                raise PageTooLargeError(
                    f"page exceeded max size limit ({total} > {self.max_page_bytes} bytes): {response.url}"
                )
            chunks.append(chunk)
        return b"".join(chunks)

    async def _collect_response_bytes_async(self, response: httpx.Response) -> bytes:
        """Collect an async response body while enforcing size limits.

        Args:
            response: Streaming async HTTPX response whose bytes should be read.

        Returns:
            The full response body as bytes when it fits within the configured
            size cap.
        """
        self._raise_if_content_length_too_large(response)
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > self.max_page_bytes:
                raise PageTooLargeError(
                    f"page exceeded max size limit ({total} > {self.max_page_bytes} bytes): {response.url}"
                )
            chunks.append(chunk)
        return b"".join(chunks)

    def _raise_if_content_length_too_large(self, response: httpx.Response) -> None:
        """Fail fast when a declared response size exceeds the configured cap.

        Args:
            response: HTTPX response whose ``Content-Length`` header should be
                checked before body consumption.

        Returns:
            None. The method raises ``PageTooLargeError`` when the declared
            content length exceeds ``self.max_page_bytes``.
        """
        content_length = response.headers.get("content-length")
        if content_length is None:
            return
        try:
            size = int(content_length)
        except ValueError:
            return
        if size > self.max_page_bytes:
            raise PageTooLargeError(
                f"page exceeded max size limit ({size} > {self.max_page_bytes} bytes): {response.url}"
            )
