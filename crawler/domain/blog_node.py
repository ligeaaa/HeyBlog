"""Crawler blog-node domain model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class BlogNode:
    """Typed view over one repository blog row used during crawling."""

    raw: dict[str, Any]
    id: int
    url: str
    domain: str

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "BlogNode":
        """Normalize one repository row into the fields used by the crawler."""
        snapshot = dict(row)
        return cls(
            raw=snapshot,
            id=int(snapshot["id"]),
            url=str(snapshot["url"]),
            domain=str(snapshot["domain"]),
        )

    def callback_payload(self) -> dict[str, Any]:
        """Return a fresh callback payload that preserves the dict contract."""
        return dict(self.raw)

