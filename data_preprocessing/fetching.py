"""Fetch page text for dataset preprocessing."""

from __future__ import annotations

from bs4 import BeautifulSoup

from agent.config import AgentSettings
from agent.schema import PageFetchOutcome
from crawler.crawling.fetching.base import FetchAttempt
from crawler.crawling.fetching.httpx_fetcher import Fetcher


class PageFetcher:
    """Fetch and normalize page content for preprocessing workflows.

    Args:
        settings: Agent runtime settings that define timeouts, concurrency,
            size caps, and the User-Agent header for HTTP fetches.
        fetcher: Optional injected fetcher for tests or custom runtimes.
    """

    def __init__(self, settings: AgentSettings, *, fetcher: Fetcher | None = None) -> None:
        self._settings = settings
        self._fetcher = fetcher or Fetcher(
            user_agent=settings.user_agent,
            timeout_seconds=settings.fetch_timeout_seconds,
            max_page_bytes=settings.max_page_bytes,
        )

    def fetch_many(self, urls: list[str]) -> dict[str, PageFetchOutcome]:
        """Fetch and normalize many URLs with one bounded-concurrency batch.

        Args:
            urls: Unique dataset URLs to fetch.

        Returns:
            A mapping from original request URLs to normalized fetch outcomes.
        """
        attempts = self._fetcher.fetch_many(
            urls,
            max_concurrency=self._settings.fetch_max_concurrency,
            timeout_seconds=self._settings.fetch_timeout_seconds,
        )
        retry_urls = [
            url
            for url, attempt in attempts.items()
            if attempt.error_kind in {"timeout", "request_error"}
        ]
        if retry_urls:
            retry_attempts = self._fetcher.fetch_many(
                retry_urls,
                max_concurrency=self._settings.fetch_max_concurrency,
                timeout_seconds=self._settings.fetch_timeout_seconds,
            )
            for url, attempt in retry_attempts.items():
                if attempt.result is not None or attempt.error_kind not in {"timeout", "request_error"}:
                    attempts[url] = attempt
        return {url: _normalize_attempt(attempt) for url, attempt in attempts.items()}


def _normalize_attempt(attempt: FetchAttempt) -> PageFetchOutcome:
    """Convert one fetch attempt into a stable preprocessing-friendly outcome.

    Args:
        attempt: Native crawler fetch attempt keyed by request URL.

    Returns:
        One normalized fetch outcome with extracted page text and failure
        semantics suitable for preprocessing.
    """
    if attempt.result is None:
        return PageFetchOutcome(
            request_url=attempt.request_url,
            final_url=None,
            page_text=None,
            fetch_status="failed",
            error_kind=attempt.error_kind,
            used_page_content=False,
        )
    return PageFetchOutcome(
        request_url=attempt.request_url,
        final_url=attempt.result.url,
        page_text=_html_to_text(attempt.result.text),
        fetch_status="success",
        error_kind=None,
        used_page_content=True,
    )


def _html_to_text(html: str) -> str:
    """Extract human-readable text from fetched HTML.

    Args:
        html: Raw HTML body returned by the crawler fetcher.

    Returns:
        One normalized plain-text string suitable for downstream modeling.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)
