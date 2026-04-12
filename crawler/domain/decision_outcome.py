"""Typed URL decision outcomes for crawler candidate handling."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class DecisionOutcome:
    """Expose one URL decision result in a strategy-friendly shape.

    Attributes:
        accepted: Whether the candidate URL should remain in the crawl flow.
        score: Numeric score preserved for compatibility with richer decision
            strategies.
        reasons: Machine-readable reason codes explaining the decision.
        hard_blocked: Whether the rejection came from a hard terminal rule.
    """

    accepted: bool
    score: float
    reasons: tuple[str, ...]
    hard_blocked: bool = False
