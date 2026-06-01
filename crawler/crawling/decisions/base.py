"""Shared types and interfaces for configurable crawler URL filters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Protocol

if TYPE_CHECKING:
    from crawler.crawling.fetching.base import FetchingStrategy

# Filters either belong to the mandatory deterministic ``rule`` AND-gate or to
# the ``success`` OR-group that runs after the rules. A candidate is kept when
# every rule filter accepts AND at least one success decider confirms it as a
# blog (or no success decider objects). See ``ConfiguredUrlFilterChain``.
DECIDER_ROLE_RULE = "rule"
DECIDER_ROLE_SUCCESS = "success"


@dataclass(slots=True, frozen=True)
class UrlCandidateContext:
    """Carry the normalized candidate URL and source metadata for filtering.

    Attributes:
        source_blog_id: Identifier of the crawled source blog that exposed this
            candidate URL.
        source_domain: Lower-cased domain of the source blog.
        normalized_url: Normalized candidate URL evaluated by the filter chain.
        link_text: Visible anchor text associated with the candidate.
        context_text: Nearby section text around the candidate anchor.
        fetcher: Optional live HTTP fetcher used by success deciders that must
            retrieve the candidate homepage (e.g. RSS discovery). Offline
            callers such as the dedup scan leave this ``None`` so network-bound
            deciders abstain instead of blocking.
        fetch_deadline: Optional ``time.monotonic()`` deadline bounding the
            per-blog crawl budget. Network-bound deciders skip fetching once it
            passes so a single blog cannot exceed its timeout budget.
    """

    source_blog_id: int
    source_domain: str
    normalized_url: str
    link_text: str = ""
    context_text: str = ""
    fetcher: "FetchingStrategy | None" = None
    fetch_deadline: float | None = None


@dataclass(slots=True, frozen=True)
class FilterDecision:
    """Represent the outcome of applying one configured URL filter.

    Attributes:
        accepted: Whether the candidate survives this filter. For ``rule``
            filters this means "continue to the next filter". For ``success``
            deciders it means "no objection" (abstain) unless ``confirmed`` is
            also set.
        status: Final status string when the filter rejects the candidate, or
            ``None`` when the candidate is accepted.
        confirmed: Whether a ``success`` decider positively identified the
            candidate as a blog. A confirm short-circuits the success group and
            keeps the candidate regardless of later deciders.
        feed_url: Discovered RSS/Atom feed URL when a success decider confirmed
            the candidate via feed discovery, otherwise ``None``.
        accepted_by: Success decider that accepted the candidate. ``rss`` marks
            feed discovery, ``model`` marks model consensus, and ``None`` means
            the candidate was not positively attributed to one success source.
    """

    accepted: bool
    status: str | None = None
    confirmed: bool = False
    feed_url: str | None = None
    accepted_by: str | None = None


class BaseUrlFilter(Protocol):
    """Define the shared contract implemented by all URL filters."""

    kind: str
    filter_kind: str
    filter_reason: str
    decider_role: str

    def apply(self, candidate: UrlCandidateContext) -> FilterDecision:
        """Return whether one normalized candidate survives this filter."""
        ...


@dataclass(slots=True)
class StaticStatusUrlFilter:
    """Provide shared helpers for filters with a fixed failure status."""

    kind: str = ""
    filter_kind: str = "rule"
    filter_reason: str = ""
    decider_role: str = DECIDER_ROLE_RULE

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

    def confirm(self, *, feed_url: str | None = None, accepted_by: str | None = None) -> FilterDecision:
        """Return the canonical confirmed decision for a success decider.

        Args:
            feed_url: Discovered feed URL to attach when the confirmation came
                from feed discovery.
            accepted_by: Machine-readable success source to persist for
                analytics, such as ``rss`` or ``model``.

        Returns:
            A decision marking the candidate as a positively identified blog.
        """
        return FilterDecision(accepted=True, status="success", confirmed=True, feed_url=feed_url, accepted_by=accepted_by)

    def decision_for(self, rejected: bool) -> FilterDecision:
        """Translate one rejection condition into the canonical decision.

        Args:
            rejected: Whether the current filter should reject the candidate.

        Returns:
            The canonical rejected decision when ``rejected`` is ``True``,
            otherwise the canonical accepted decision.
        """
        if rejected:
            return self.reject()
        return self.accept()
