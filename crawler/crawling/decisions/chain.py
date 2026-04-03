"""Composable decision chain for crawler candidate handling."""

from __future__ import annotations

from dataclasses import dataclass

from crawler.crawling.decisions.base import UrlDecisionStep
from crawler.domain.decision_outcome import DecisionOutcome


@dataclass(slots=True)
class UrlDecisionChain:
    """Run URL decision steps sequentially until one rejects the candidate."""

    steps: tuple[UrlDecisionStep, ...]

    def decide(
        self,
        url: str,
        source_domain: str,
        *,
        link_text: str = "",
        context_text: str = "",
    ) -> DecisionOutcome:
        """Return the combined outcome of the configured decision steps."""
        last_decision = DecisionOutcome(accepted=True, score=0.0, reasons=())
        for step in self.steps:
            last_decision = step.decide(
                url,
                source_domain,
                link_text=link_text,
                context_text=context_text,
            )
            if not last_decision.accepted:
                return last_decision
        return last_decision

