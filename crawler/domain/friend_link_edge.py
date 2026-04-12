"""Crawler edge / friend-link domain model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class FriendLinkEdge:
    """Represent a discovered outbound blog-to-blog edge.

    Attributes:
        from_blog_id: Source blog that published the friend link.
        to_blog_id: Target blog discovered through the friend link.
        link_url_raw: Raw URL exactly as extracted from the source page.
        link_text: Visible anchor text associated with the edge, if any.
    """

    from_blog_id: int
    to_blog_id: int
    link_url_raw: str
    link_text: str | None
