"""Fetch result shapes and fetcher protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class PageTooLargeError(Exception):
    """Signal that one HTTP response exceeded the configured crawler size cap.

    This exception is raised by fetcher implementations when the response body
    grows beyond the permitted byte budget while being read.
    """


@dataclass(slots=True)
class FetchResult:
    """Represent a successful HTTP fetch response used by crawler callers.

    Attributes:
        url: Final response URL after redirects, used as the canonical fetched
            page location for downstream parsing.
        status_code: HTTP status code returned for the successful request.
        text: Decoded response body text that discovery, extraction, and
            metadata code will parse.
    """

    url: str
    status_code: int
    text: str


@dataclass(slots=True)
class FetchAttempt:
    """Represent one batch fetch outcome keyed by the original request URL.

    Attributes:
        request_url: Original URL requested by the batch fetch call, preserved
            so callers can map results back onto discovery order.
        result: Parsed fetch result when the request succeeded, otherwise
            ``None``.
        error_kind: Stable error classification for failed attempts, or
            ``None`` when the request succeeded.
    """

    request_url: str
    result: FetchResult | None
    error_kind: str | None


class FetchingStrategy(Protocol):
    """Describe the fetch operations required by the crawler pipeline.

    Implementations are responsible for retrieving one or more URLs and
    returning shapes that the pipeline and orchestrator can consume without
    knowing the underlying HTTP client details.
    """

    def fetch(self, url: str, *, timeout_seconds: float | None = None) -> FetchResult:
        """Fetch a single URL for crawler processing.

        Args:
            url: Absolute URL to retrieve.
            timeout_seconds: Optional per-request timeout override in seconds.

        Returns:
            A ``FetchResult`` describing the successful response.
        """
        ...

    def fetch_many(
        self,
        urls: list[str],
        *,
        max_concurrency: int,
        timeout_seconds: float | None = None,
    ) -> dict[str, FetchAttempt]:
        """Fetch multiple URLs while preserving the original request keys.

        Args:
            urls: Absolute URLs to retrieve as one batch.
            max_concurrency: Maximum number of concurrent in-flight requests.
            timeout_seconds: Optional timeout override applied to each request.

        Returns:
            A mapping from each original request URL to its corresponding
            ``FetchAttempt`` result.
        """
        ...
