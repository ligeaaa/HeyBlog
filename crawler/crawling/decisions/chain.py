"""Composable decision chain for crawler candidate handling."""

from __future__ import annotations

from dataclasses import dataclass

from crawler.crawling.decisions.base import UrlDecisionStep
from crawler.crawling.decisions.consensus import ModelConsensusDecider
from crawler.crawling.decisions.rules import RuleBasedDecider
from crawler.domain.decision_outcome import DecisionOutcome
from shared.config import Settings


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


def build_url_decision_chain(settings: Settings) -> UrlDecisionChain:
    """Build the canonical URL decision chain for crawler-style filtering.

    Args:
        settings: Shared runtime settings containing hard-rule blocklists and
            optional model-consensus configuration.

    Returns:
        The canonical ``UrlDecisionChain`` used for both live crawling and
        administrative rescan workflows.
    """
    steps: list[UrlDecisionStep] = [
        RuleBasedDecider(
            domain_blocklist=settings.friend_link_domain_blocklist,
            blocked_tlds=settings.friend_link_tld_blocklist,
            exact_url_blocklist=settings.friend_link_exact_url_blocklist,
            prefix_blocklist=settings.friend_link_prefix_blocklist,
        )
    ]
    if settings.decision_model_consensus_enabled:
        # Model consensus is an additional filter layer after deterministic
        # hard-rule blocking so administrative rescans stay aligned with live
        # crawler link acceptance.
        steps.append(ModelConsensusDecider(model_root=settings.decision_model_root))
    return UrlDecisionChain(steps=tuple(steps))
