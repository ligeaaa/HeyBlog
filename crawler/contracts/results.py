"""Typed result containers used inside the crawler application flow."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class BlogCrawlResult:
    """Represent the persisted outcome of crawling one blog homepage.

    Attributes:
        status_code: HTTP status code returned for the crawled homepage.
        discovered_count: Number of accepted friend-link targets discovered for
            the blog.
        title: Extracted site title, if one was found on the homepage.
        icon_url: Extracted icon URL, if one was found on the homepage.
    """

    status_code: int
    discovered_count: int
    title: str | None
    icon_url: str | None


@dataclass(slots=True)
class CrawlRunStats:
    """Accumulate counters for one synchronous pipeline batch.

    Attributes:
        processed: Number of blogs attempted so far in the batch.
        discovered: Number of accepted child blog links discovered so far.
        failed: Number of blogs that failed during processing.
    """

    processed: int = 0
    discovered: int = 0
    failed: int = 0

    def record_success(self, discovered_count: int) -> None:
        """Record one successful blog crawl in the batch counters.

        Args:
            discovered_count: Number of child blog links discovered while
                processing the successful blog.

        Returns:
            ``None``. The batch counters are updated in place.
        """
        self.processed += 1
        self.discovered += discovered_count

    def record_failure(self) -> None:
        """Record one failed blog crawl in the batch counters.

        Returns:
            ``None``. The batch counters are updated in place.
        """
        self.processed += 1
        self.failed += 1
