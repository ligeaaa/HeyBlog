"""Decision interfaces for crawler candidate filtering."""

from __future__ import annotations

from typing import Protocol

from crawler.domain.decision_outcome import DecisionOutcome


class UrlDecisionStep(Protocol):
    """Define one pluggable decision step for discovered crawler URLs.

    Implementations receive one discovered link plus source-context data and
    return a ``DecisionOutcome`` describing whether the candidate should remain
    in the pipeline.
    """

    def decide(
        self,
        url: str,
        source_domain: str,
        *,
        link_text: str = "",
        context_text: str = "",
    ) -> DecisionOutcome:
        """Evaluate whether one discovered URL should remain a crawler candidate.

        Args:
            url: Extracted absolute URL being evaluated.
            source_domain: Domain of the blog page from which the URL was
                discovered.
            link_text: Visible anchor text associated with the URL.
            context_text: Nearby container text describing the surrounding page
                context.

        Returns:
            A ``DecisionOutcome`` describing acceptance, score, and reason codes.
        """
        ...
