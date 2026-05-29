"""Crawler capacity guardrails backed by persistence counters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CrawlerCapacityState:
    """Describe whether crawler work may start under the raw URL limit.

    Attributes:
        allowed: Whether crawler work may claim or process another blog.
        raw_count: Current ``raw_discovered_urls`` row count when available.
        limit: Configured raw URL limit. ``-1`` disables the guard.
        reason: Machine-readable reason for blocked capacity, or ``None``.
    """

    allowed: bool
    raw_count: int | None
    limit: int
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serialize the capacity state for API/runtime payloads.

        Returns:
            Dictionary containing the guard decision and observed counters.
        """

        return {
            "allowed": self.allowed,
            "raw_count": self.raw_count,
            "limit": self.limit,
            "reason": self.reason,
        }


class CrawlerCapacityGate:
    """Stop crawler starts once ``raw_discovered_urls`` reaches a limit.

    Args:
        repository: Persistence boundary exposing ``stats`` or
            ``get_filter_stats_by_chain_order``.
        raw_discovered_url_limit: Maximum allowed raw URL rows. ``-1``
            disables the guard.

    Returns:
        A reusable gate object that reads counters without mutating state.
    """

    def __init__(self, repository: Any, *, raw_discovered_url_limit: int) -> None:
        self.repository = repository
        self.raw_discovered_url_limit = raw_discovered_url_limit

    def check(self) -> CrawlerCapacityState:
        """Return whether crawler work is still allowed.

        Returns:
            Capacity decision based on the current raw URL count. Missing raw
            stats are treated as allowed so old test doubles remain compatible.
        """

        limit = int(self.raw_discovered_url_limit)
        if limit == -1:
            return CrawlerCapacityState(allowed=True, raw_count=None, limit=limit)

        raw_count = self._raw_discovered_url_count()
        if raw_count is None or raw_count < limit:
            return CrawlerCapacityState(allowed=True, raw_count=raw_count, limit=limit)
        return CrawlerCapacityState(
            allowed=False,
            raw_count=raw_count,
            limit=limit,
            reason="raw_discovered_url_limit_reached",
        )

    def ensure_allowed(self) -> CrawlerCapacityState:
        """Return capacity state or raise when the crawler must stay closed.

        Returns:
            Allowed capacity state.

        Raises:
            RuntimeError: Raised when the raw URL count has reached the
                configured limit.
        """

        state = self.check()
        if not state.allowed:
            raise RuntimeError(
                "raw_discovered_url_limit_reached: "
                f"raw_discovered_urls={state.raw_count}, limit={state.limit}"
            )
        return state

    def _raw_discovered_url_count(self) -> int | None:
        """Read the current raw URL count from persistence.

        Returns:
            Raw URL count when the repository exposes it, otherwise ``None``.
        """

        stats_getter = getattr(self.repository, "stats", None)
        if stats_getter is not None:
            stats = stats_getter()
            raw_count = stats.get("raw_discovered_urls")
            if raw_count is not None:
                return int(raw_count)

        filter_stats_getter = getattr(self.repository, "get_filter_stats_by_chain_order", None)
        if filter_stats_getter is None:
            filter_stats_getter = getattr(self.repository, "filter_stats", None)
        if filter_stats_getter is None:
            return None

        filter_stats = filter_stats_getter()
        by_filter_reason = filter_stats.get("by_filter_reason", {})
        raw_count = by_filter_reason.get("raw")
        return int(raw_count) if raw_count is not None else None
