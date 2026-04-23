"""Concrete rule-based URL filters used by the configurable filter chain."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from crawler.crawling.decisions.base import FilterDecision
from crawler.crawling.decisions.base import StaticStatusUrlFilter
from crawler.crawling.decisions.base import UrlCandidateContext
from crawler.filters import BLOCKED_TLDS
from crawler.filters import FILE_SUFFIX_BLOCKLIST
from crawler.filters import PATH_BLOCKLIST
from crawler.filters import PLATFORM_BLOCKLIST


def _matches_blocked_domain(domain: str, blocklist: tuple[str, ...] | set[str]) -> bool:
    """Return whether a domain exactly matches or is nested under a blocked domain."""
    return any(domain == blocked or domain.endswith(f".{blocked}") for blocked in blocklist)


def _matches_exact_url(normalized_url: str, exact_url_blocklist: tuple[str, ...]) -> bool:
    """Return whether a normalized URL is explicitly blocked."""
    normalized_blocklist = {value.rstrip("/") for value in exact_url_blocklist}
    return normalized_url.rstrip("/") in normalized_blocklist


@dataclass(slots=True)
class NonHttpSchemeFilter(StaticStatusUrlFilter):
    """Reject candidate URLs that do not use HTTP(S)."""

    kind: str = "non_http_scheme"
    filter_kind: str = "rule"
    filter_reason: str = "non_http_scheme"

    def apply(self, candidate: UrlCandidateContext) -> FilterDecision:
        parsed = urlparse(candidate.normalized_url)
        if not parsed.scheme.startswith("http"):
            return self.reject()
        return self.accept()


@dataclass(slots=True)
class SameDomainFilter(StaticStatusUrlFilter):
    """Reject candidates that remain on the source blog's own domain."""

    kind: str = "same_domain"
    filter_kind: str = "rule"
    filter_reason: str = "same_domain"

    def apply(self, candidate: UrlCandidateContext) -> FilterDecision:
        domain = urlparse(candidate.normalized_url).netloc.lower()
        if not domain or domain == candidate.source_domain.lower():
            return self.reject()
        return self.accept()


@dataclass(slots=True)
class ExactUrlBlocklistFilter(StaticStatusUrlFilter):
    """Reject candidates whose normalized URL exactly matches a blocked value."""

    exact_url_blocklist: tuple[str, ...] = ()
    kind: str = "exact_url_blocklist"
    filter_kind: str = "rule"
    filter_reason: str = "exact_url_blocked"

    def apply(self, candidate: UrlCandidateContext) -> FilterDecision:
        if _matches_exact_url(candidate.normalized_url, self.exact_url_blocklist):
            return self.reject()
        return self.accept()


@dataclass(slots=True)
class PrefixBlocklistFilter(StaticStatusUrlFilter):
    """Reject candidates that start with a blocked normalized prefix."""

    prefix_blocklist: tuple[str, ...] = ()
    kind: str = "prefix_blocklist"
    filter_kind: str = "rule"
    filter_reason: str = "prefix_blocked"

    def apply(self, candidate: UrlCandidateContext) -> FilterDecision:
        normalized_url = candidate.normalized_url.rstrip("/")
        if any(normalized_url.startswith(prefix.rstrip("/")) for prefix in self.prefix_blocklist):
            return self.reject()
        return self.accept()


@dataclass(slots=True)
class PlatformDomainFilter(StaticStatusUrlFilter):
    """Reject candidates that point to known platform domains."""

    kind: str = "platform_domain"
    filter_kind: str = "rule"
    filter_reason: str = "platform_blocked"

    def apply(self, candidate: UrlCandidateContext) -> FilterDecision:
        domain = urlparse(candidate.normalized_url).netloc.lower()
        if _matches_blocked_domain(domain, PLATFORM_BLOCKLIST):
            return self.reject()
        return self.accept()


@dataclass(slots=True)
class CustomDomainBlocklistFilter(StaticStatusUrlFilter):
    """Reject candidates that match one of the configured blocked domains."""

    domain_blocklist: tuple[str, ...] = ()
    kind: str = "custom_domain_blocklist"
    filter_kind: str = "rule"
    filter_reason: str = "domain_blocked"

    def apply(self, candidate: UrlCandidateContext) -> FilterDecision:
        domain = urlparse(candidate.normalized_url).netloc.lower()
        if _matches_blocked_domain(domain, self.domain_blocklist):
            return self.reject()
        return self.accept()


@dataclass(slots=True)
class BlockedTldFilter(StaticStatusUrlFilter):
    """Reject candidates whose host ends with a blocked TLD suffix."""

    blocked_tlds: tuple[str, ...] = BLOCKED_TLDS
    kind: str = "blocked_tld"
    filter_kind: str = "rule"
    filter_reason: str = "blocked_tld"

    def apply(self, candidate: UrlCandidateContext) -> FilterDecision:
        domain = urlparse(candidate.normalized_url).netloc.lower()
        if any(domain.endswith(tld) for tld in self.blocked_tlds):
            return self.reject()
        return self.accept()


@dataclass(slots=True)
class RootPathFilter(StaticStatusUrlFilter):
    """Reject candidates that do not look like a site root URL."""

    kind: str = "root_path"
    filter_kind: str = "rule"
    filter_reason: str = "non_root_path"

    def apply(self, candidate: UrlCandidateContext) -> FilterDecision:
        path = urlparse(candidate.normalized_url).path or "/"
        if path != "/":
            return self.reject()
        return self.accept()


@dataclass(slots=True)
class LocationFragmentFilter(StaticStatusUrlFilter):
    """Reject candidates that still carry query-string or fragment state."""

    kind: str = "location_fragment"
    filter_kind: str = "rule"
    filter_reason: str = "non_root_location"

    def apply(self, candidate: UrlCandidateContext) -> FilterDecision:
        parsed = urlparse(candidate.normalized_url)
        if parsed.query or parsed.fragment:
            return self.reject()
        return self.accept()


@dataclass(slots=True)
class AssetSuffixFilter(StaticStatusUrlFilter):
    """Reject candidate paths that end with a static-asset-like suffix."""

    kind: str = "asset_suffix"
    filter_kind: str = "rule"
    filter_reason: str = "asset_suffix"

    def apply(self, candidate: UrlCandidateContext) -> FilterDecision:
        path = (urlparse(candidate.normalized_url).path or "/").lower()
        if any(path.endswith(suffix) for suffix in FILE_SUFFIX_BLOCKLIST):
            return self.reject()
        return self.accept()


@dataclass(slots=True)
class BlockedPathFilter(StaticStatusUrlFilter):
    """Reject candidate paths that match obvious non-homepage prefixes."""

    kind: str = "blocked_path"
    filter_kind: str = "rule"
    filter_reason: str = "blocked_path"

    def apply(self, candidate: UrlCandidateContext) -> FilterDecision:
        lowered = (urlparse(candidate.normalized_url).path or "/").lower()
        if any(lowered == blocked or lowered.startswith(f"{blocked}/") for blocked in PATH_BLOCKLIST):
            return self.reject()
        return self.accept()
