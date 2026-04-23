"""Concrete rule-based URL filters used by the configurable filter chain."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from crawler.crawling.decisions.base import FilterDecision
from crawler.crawling.decisions.base import StaticStatusUrlFilter
from crawler.crawling.decisions.base import UrlCandidateContext
from crawler.crawling.decisions.rule_helpers import BLOCKED_TLDS
from crawler.crawling.decisions.rule_helpers import PLATFORM_BLOCKLIST
from crawler.crawling.decisions.rule_helpers import has_asset_suffix
from crawler.crawling.decisions.rule_helpers import has_extra_location_parts
from crawler.crawling.decisions.rule_helpers import is_root_like_path
from crawler.crawling.decisions.rule_helpers import matches_blocked_domain
from crawler.crawling.decisions.rule_helpers import matches_exact_url
from crawler.crawling.decisions.rule_helpers import matches_prefix_blocklist
from crawler.crawling.decisions.rule_helpers import path_has_blocked_segment


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
        if matches_exact_url(candidate.normalized_url, self.exact_url_blocklist):
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
        if matches_prefix_blocklist(candidate.normalized_url, self.prefix_blocklist):
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
        if matches_blocked_domain(domain, PLATFORM_BLOCKLIST):
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
        if matches_blocked_domain(domain, self.domain_blocklist):
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
        if not is_root_like_path(urlparse(candidate.normalized_url).path):
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
        if has_extra_location_parts(query=parsed.query, fragment=parsed.fragment):
            return self.reject()
        return self.accept()


@dataclass(slots=True)
class AssetSuffixFilter(StaticStatusUrlFilter):
    """Reject candidate paths that end with a static-asset-like suffix."""

    kind: str = "asset_suffix"
    filter_kind: str = "rule"
    filter_reason: str = "asset_suffix"

    def apply(self, candidate: UrlCandidateContext) -> FilterDecision:
        if has_asset_suffix(urlparse(candidate.normalized_url).path):
            return self.reject()
        return self.accept()


@dataclass(slots=True)
class BlockedPathFilter(StaticStatusUrlFilter):
    """Reject candidate paths that match obvious non-homepage prefixes."""

    kind: str = "blocked_path"
    filter_kind: str = "rule"
    filter_reason: str = "blocked_path"

    def apply(self, candidate: UrlCandidateContext) -> FilterDecision:
        if path_has_blocked_segment(urlparse(candidate.normalized_url).path or "/"):
            return self.reject()
        return self.accept()
