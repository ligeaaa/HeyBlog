"""Typed URL decision outcomes for crawler candidate handling."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class DecisionOutcome:
    """Expose one URL decision result in a strategy-friendly shape."""

    accepted: bool
    score: float
    reasons: tuple[str, ...]
    hard_blocked: bool = False

