"""Rule-based URL decision step wrapping the legacy crawler filters."""

from __future__ import annotations

from dataclasses import dataclass

from crawler.domain.decision_outcome import DecisionOutcome
from crawler.filters import LinkDecision
from crawler.filters import decide_blog_candidate


@dataclass(slots=True)
class RuleBasedDecider:
    """Apply the existing deterministic crawler rules through a strategy seam."""

    domain_blocklist: tuple[str, ...] = ()
    blocked_tlds: tuple[str, ...] = ()
    exact_url_blocklist: tuple[str, ...] = ()
    prefix_blocklist: tuple[str, ...] = ()

    def decide(
        self,
        url: str,
        source_domain: str,
        *,
        link_text: str = "",
        context_text: str = "",
    ) -> DecisionOutcome:
        """Return the existing deterministic filtering outcome."""
        kwargs = {
            "link_text": link_text,
            "context_text": context_text,
            "domain_blocklist": self.domain_blocklist,
            "exact_url_blocklist": self.exact_url_blocklist,
            "prefix_blocklist": self.prefix_blocklist,
        }
        if self.blocked_tlds:
            kwargs["blocked_tlds"] = self.blocked_tlds

        decision: LinkDecision = decide_blog_candidate(url, source_domain, **kwargs)
        return DecisionOutcome(
            accepted=decision.accepted,
            score=decision.score,
            reasons=decision.reasons,
            hard_blocked=decision.hard_blocked,
        )

