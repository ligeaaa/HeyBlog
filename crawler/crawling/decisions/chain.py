"""Composable decision chain for crawler candidate handling."""

from __future__ import annotations

from dataclasses import dataclass

from crawler.crawling.decisions.base import UrlDecisionStep
from crawler.domain.decision_outcome import DecisionOutcome


@dataclass(slots=True)
class UrlDecisionChain:
    """Run a sequence of URL decision steps against one extracted link.

    Attributes:
        steps: Ordered decision-step implementations that are executed in
            sequence until one rejects the candidate.
    """

    steps: tuple[UrlDecisionStep, ...]

    def decide(
        self,
        url: str,
        source_domain: str,
        *,
        link_text: str = "",
        context_text: str = "",
    ) -> DecisionOutcome:
        """Evaluate one URL through the configured decision-step chain.

        Args:
            url: Absolute extracted URL being evaluated.
            source_domain: Domain of the page from which the URL was extracted.
            link_text: Visible anchor text associated with the URL.
            context_text: Nearby surrounding text that may help future
                strategies classify the link.

        Returns:
            The first rejecting ``DecisionOutcome`` in the chain, or the final
            accepting outcome if every step allows the candidate through.
        """
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
