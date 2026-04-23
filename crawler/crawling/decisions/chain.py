"""Configurable URL filter-chain loading and compatibility helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any

from crawler.crawling.decisions.base import BaseUrlFilter
from crawler.crawling.decisions.base import FilterDecision
from crawler.crawling.decisions.base import UrlCandidateContext
from crawler.crawling.decisions.consensus import ModelConsensusFilter
from crawler.crawling.decisions.filters import AssetSuffixFilter
from crawler.crawling.decisions.filters import BlockedPathFilter
from crawler.crawling.decisions.filters import BlockedTldFilter
from crawler.crawling.decisions.filters import CustomDomainBlocklistFilter
from crawler.crawling.decisions.filters import ExactUrlBlocklistFilter
from crawler.crawling.decisions.filters import LocationFragmentFilter
from crawler.crawling.decisions.filters import NonHttpSchemeFilter
from crawler.crawling.decisions.filters import PlatformDomainFilter
from crawler.crawling.decisions.filters import PrefixBlocklistFilter
from crawler.crawling.decisions.filters import RootPathFilter
from crawler.crawling.decisions.filters import SameDomainFilter
from crawler.crawling.normalization import normalize_url
from crawler.domain.decision_outcome import DecisionOutcome
from shared.config import Settings


FilterFactory = Any


def _build_non_http_scheme_filter(settings: Settings) -> BaseUrlFilter:
    del settings
    return NonHttpSchemeFilter()


def _build_same_domain_filter(settings: Settings) -> BaseUrlFilter:
    del settings
    return SameDomainFilter()


def _build_exact_url_blocklist_filter(settings: Settings) -> BaseUrlFilter:
    return ExactUrlBlocklistFilter(exact_url_blocklist=settings.friend_link_exact_url_blocklist)


def _build_prefix_blocklist_filter(settings: Settings) -> BaseUrlFilter:
    return PrefixBlocklistFilter(prefix_blocklist=settings.friend_link_prefix_blocklist)


def _build_platform_domain_filter(settings: Settings) -> BaseUrlFilter:
    del settings
    return PlatformDomainFilter()


def _build_custom_domain_blocklist_filter(settings: Settings) -> BaseUrlFilter:
    return CustomDomainBlocklistFilter(domain_blocklist=settings.friend_link_domain_blocklist)


def _build_blocked_tld_filter(settings: Settings) -> BaseUrlFilter:
    blocked_tlds = settings.friend_link_tld_blocklist or BlockedTldFilter().blocked_tlds
    return BlockedTldFilter(blocked_tlds=blocked_tlds)


def _build_root_path_filter(settings: Settings) -> BaseUrlFilter:
    del settings
    return RootPathFilter()


def _build_location_fragment_filter(settings: Settings) -> BaseUrlFilter:
    del settings
    return LocationFragmentFilter()


def _build_asset_suffix_filter(settings: Settings) -> BaseUrlFilter:
    del settings
    return AssetSuffixFilter()


def _build_blocked_path_filter(settings: Settings) -> BaseUrlFilter:
    del settings
    return BlockedPathFilter()


def _build_model_consensus_filter(settings: Settings) -> BaseUrlFilter:
    return ModelConsensusFilter(model_root=settings.decision_model_root)


FILTER_REGISTRY: dict[str, FilterFactory] = {
    "non_http_scheme": _build_non_http_scheme_filter,
    "same_domain": _build_same_domain_filter,
    "exact_url_blocklist": _build_exact_url_blocklist_filter,
    "prefix_blocklist": _build_prefix_blocklist_filter,
    "platform_domain": _build_platform_domain_filter,
    "custom_domain_blocklist": _build_custom_domain_blocklist_filter,
    "blocked_tld": _build_blocked_tld_filter,
    "root_path": _build_root_path_filter,
    "location_fragment": _build_location_fragment_filter,
    "asset_suffix": _build_asset_suffix_filter,
    "blocked_path": _build_blocked_path_filter,
    "model_consensus": _build_model_consensus_filter,
}

DEFAULT_FILTER_KINDS = (
    "non_http_scheme",
    "same_domain",
    "exact_url_blocklist",
    "prefix_blocklist",
    "platform_domain",
    "custom_domain_blocklist",
    "blocked_tld",
    "root_path",
    "location_fragment",
    "asset_suffix",
    "blocked_path",
    "model_consensus",
)


def _load_filter_chain_config(path: Path) -> list[dict[str, Any]]:
    """Read one TOML filter-chain config file or return the default ordering."""
    if not path.exists():
        return [{"kind": kind, "enabled": True} for kind in DEFAULT_FILTER_KINDS]
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    configured = payload.get("filters", [])
    if not isinstance(configured, list):
        raise ValueError("filter_chain_config_invalid")
    return [item for item in configured if isinstance(item, dict)]


@dataclass(slots=True)
class ConfiguredUrlFilterChain:
    """Evaluate one candidate URL through the configured filter sequence."""

    filters: tuple[BaseUrlFilter, ...]

    @property
    def steps(self) -> tuple[BaseUrlFilter, ...]:
        """Expose the configured filters under the legacy `steps` name."""
        return self.filters

    @classmethod
    def from_settings(cls, settings: Settings) -> "ConfiguredUrlFilterChain":
        """Build a filter chain using the configured TOML ordering."""
        loaded_filters: list[BaseUrlFilter] = []
        for item in _load_filter_chain_config(settings.filter_chain_config_path):
            if not bool(item.get("enabled", True)):
                continue
            kind = str(item.get("kind", "")).strip()
            factory = FILTER_REGISTRY.get(kind)
            if factory is None:
                raise ValueError(f"unknown_filter_kind:{kind}")
            loaded_filters.append(factory(settings))
        return cls(filters=tuple(loaded_filters))

    def evaluate(self, candidate: UrlCandidateContext) -> FilterDecision:
        """Return the first rejecting filter decision or ``success``."""
        for url_filter in self.filters:
            decision = url_filter.apply(candidate)
            if not decision.accepted:
                return decision
        return FilterDecision(accepted=True, status="success")

    def ordered_statuses(self) -> list[str]:
        """Return filter status keys in execution order."""
        return [f"{url_filter.filter_kind}:{url_filter.filter_reason}" for url_filter in self.filters]

    def decide(
        self,
        url: str,
        source_domain: str,
        *,
        link_text: str = "",
        context_text: str = "",
    ) -> DecisionOutcome:
        """Provide the legacy decision outcome for older call sites."""
        del link_text
        del context_text
        decision = self.evaluate(
            UrlCandidateContext(
                source_blog_id=0,
                source_domain=source_domain,
                normalized_url=normalize_url(url).normalized_url,
            )
        )
        if decision.accepted:
            return DecisionOutcome(accepted=True, score=0.0, reasons=("passed_filter_chain",))
        _, _, reason = str(decision.status).partition(":")
        return DecisionOutcome(accepted=False, score=0.0, reasons=(reason or "filter_rejected",), hard_blocked=True)


def build_url_decision_chain(settings: Settings) -> ConfiguredUrlFilterChain:
    """Build the configured URL filter chain used by crawler and rescans."""
    return ConfiguredUrlFilterChain.from_settings(settings)
