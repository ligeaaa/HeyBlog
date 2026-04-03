"""Typed result containers used inside the crawler application flow."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class BlogCrawlResult:
    """Represent the persisted outcome of crawling one blog homepage."""

    status_code: int
    discovered_count: int
    title: str | None
    icon_url: str | None


@dataclass(slots=True)
class CrawlRunStats:
    """Accumulate batch counters for one pipeline run."""

    processed: int = 0
    discovered: int = 0
    failed: int = 0

    def record_success(self, discovered_count: int) -> None:
        """Account for one successfully processed blog."""
        self.processed += 1
        self.discovered += discovered_count

    def record_failure(self) -> None:
        """Account for one failed blog."""
        self.processed += 1
        self.failed += 1

