"""Optional MCP-ready classifier boundary for ambiguous friend-link cases."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from app.config import Settings
from app.crawler.extractor import ExtractedLink


@dataclass(slots=True)
class ClassifierLinkDecision:
    """Represent a model-assisted decision for one extracted link."""

    url: str
    accepted: bool
    confidence: float
    reason: str


@dataclass(slots=True)
class ClassifierResult:
    """Represent a bounded classifier response."""

    available: bool
    selected_links: tuple[ClassifierLinkDecision, ...]
    reason: str


class ClassifierUnavailableError(RuntimeError):
    """Raised when the optional classifier cannot be used."""


class FriendLinkClassifier:
    """Optional adapter boundary for ambiguous page and link review."""

    def __init__(self, *, timeout_seconds: float, max_links: int) -> None:
        """Store the runtime budget for later classifier implementations."""
        self.timeout_seconds = timeout_seconds
        self.max_links = max_links

    def build_cache_key(self, page_url: str, page_html: str) -> str:
        """Return a stable cache key for a page URL and content body."""
        digest = sha256(page_html.encode("utf-8")).hexdigest()
        return f"{page_url}:{digest}"

    def review_links(self, page_url: str, page_html: str, links: list[ExtractedLink]) -> ClassifierResult:
        """Review ambiguous links or raise when no remote classifier is configured."""
        _ = self.build_cache_key(page_url, page_html)
        _ = links[: self.max_links]
        raise ClassifierUnavailableError("MCP classifier not configured")


def build_classifier(settings: Settings) -> FriendLinkClassifier | None:
    """Return a disabled-by-default classifier adapter."""
    if not settings.enable_mcp_classifier:
        return None
    return FriendLinkClassifier(
        timeout_seconds=settings.classifier_timeout_seconds,
        max_links=settings.max_links_for_mcp_review,
    )
