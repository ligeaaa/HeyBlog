"""Crawler state model helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class CrawlState:
    """Represent persisted crawl state for one blog node."""

    status: str
    status_code: int | None = None
    friend_links_count: int = 0
    metadata_captured: bool = False
    title: str | None = None
    icon_url: str | None = None

