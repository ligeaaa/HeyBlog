"""Crawler edge / friend-link domain model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class FriendLinkEdge:
    """Represent a discovered outbound blog edge."""

    from_blog_id: int
    to_blog_id: int
    link_url_raw: str
    link_text: str | None

