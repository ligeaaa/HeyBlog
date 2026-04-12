"""Crawler state model helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class CrawlState:
    """Represent the persisted crawl state written back for one blog node.

    Attributes:
        status: Final crawl status such as ``FINISHED`` or ``FAILED``.
        status_code: HTTP status code associated with the crawl, when known.
        friend_links_count: Number of accepted outbound blog links discovered.
        metadata_captured: Whether title/icon metadata was successfully stored.
        title: Extracted page title, if available.
        icon_url: Extracted icon URL, if available.
    """

    status: str
    status_code: int | None = None
    friend_links_count: int = 0
    metadata_captured: bool = False
    title: str | None = None
    icon_url: str | None = None
