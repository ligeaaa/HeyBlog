"""Shared types and interfaces for configurable crawler URL filters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True, frozen=True)
class UrlCandidateContext:
    """Carry the normalized candidate URL and source metadata for filtering.

    Attributes:
        source_blog_id: Identifier of the crawled source blog that exposed this
            candidate URL.
        source_domain: Lower-cased domain of the source blog.
        normalized_url: Normalized candidate URL evaluated by the filter chain.
    """

    source_blog_id: int
    source_domain: str
    normalized_url: str


@dataclass(slots=True, frozen=True)
class FilterDecision:
    """Represent the outcome of applying one configured URL filter.

    Attributes:
        accepted: Whether the candidate should continue to the next filter.
        status: Final status string when the filter rejects the candidate, or
            ``None`` when the candidate is accepted.
    """

    accepted: bool
    status: str | None = None


class BaseUrlFilter(Protocol):
    """Define the shared contract implemented by all URL filters."""

    kind: str
    filter_kind: str
    filter_reason: str

    def apply(self, candidate: UrlCandidateContext) -> FilterDecision:
        """Return whether one normalized candidate survives this filter."""
        ...


@dataclass(slots=True)
class StaticStatusUrlFilter:
    """Provide shared helpers for filters with a fixed failure status."""

    kind: str = ""
    filter_kind: str = "rule"
    filter_reason: str = ""

    @property
    def status(self) -> str:
        """Return the public status string emitted when this filter rejects."""
        return f"{self.filter_kind}:{self.filter_reason}"

    def accept(self) -> FilterDecision:
        """Return the canonical accepted decision for this filter."""
        return FilterDecision(accepted=True, status=None)

    def reject(self) -> FilterDecision:
        """Return the canonical rejected decision for this filter."""
        return FilterDecision(accepted=False, status=self.status)
