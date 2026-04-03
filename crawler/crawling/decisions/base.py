"""Decision interfaces for crawler candidate filtering."""

from __future__ import annotations

from typing import Protocol

from crawler.domain.decision_outcome import DecisionOutcome


class UrlDecisionStep(Protocol):
    """Evaluate whether a discovered URL should remain a crawler candidate."""

    def decide(
        self,
        url: str,
        source_domain: str,
        *,
        link_text: str = "",
        context_text: str = "",
    ) -> DecisionOutcome: ...

