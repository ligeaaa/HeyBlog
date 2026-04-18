"""Crawler blog-node domain model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class BlogNode:
    """Typed view over one repository blog row used during crawling.

    Attributes:
        raw: Original repository row preserved for callbacks and compatibility
            callers.
        id: Blog identifier used by persistence operations.
        url: Canonical blog URL to crawl.
        domain: Domain portion associated with the blog URL.
    """

    raw: dict[str, Any]
    id: int
    url: str
    domain: str

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "BlogNode":
        """Build a typed blog node from a repository row.

        Args:
            row: Repository row containing at least ``id``, ``url``, and
                ``domain`` fields.

        Returns:
            A ``BlogNode`` snapshot with a copied raw payload and normalized
            scalar fields.
        """
        snapshot = dict(row)
        return cls(
            raw=snapshot,
            id=int(snapshot["id"]),
            url=str(snapshot["url"]),
            domain=str(snapshot["domain"]),
        )

    def callback_payload(self) -> dict[str, Any]:
        """Return a fresh dictionary payload for legacy callback consumers.

        Returns:
            A shallow copy of the original repository row.
        """
        return dict(self.raw)
