"""Configurable URL filter-chain loading and compatibility helpers."""

from __future__ import annotations

from collections.abc import Callable
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


FilterFactory = Callable[[Settings], BaseUrlFilter]


def _static_filter_factory(filter_cls: type[BaseUrlFilter]) -> FilterFactory:
    """Build a registry factory for filters that ignore settings entirely.

    Args:
        filter_cls: Filter class instantiated without constructor arguments.

    Returns:
        Factory callable that discards settings and returns one filter instance.
    """

    def build_filter(settings: Settings) -> BaseUrlFilter:
        del settings
        return filter_cls()

    return build_filter


def _settings_value_filter_factory(
    filter_cls: type[BaseUrlFilter],
    *,
    setting_attr: str,
    constructor_kwarg: str,
) -> FilterFactory:
    """Build a registry factory for filters that forward one settings value.

    Args:
        filter_cls: Filter class instantiated with exactly one keyword argument.
        setting_attr: Settings attribute name read from `Settings`.
        constructor_kwarg: Keyword name forwarded into the filter constructor.

    Returns:
        Factory callable that pulls one settings value and injects it into the
        configured filter class.
    """

    def build_filter(settings: Settings) -> BaseUrlFilter:
        return filter_cls(**{constructor_kwarg: getattr(settings, setting_attr)})

    return build_filter


def _build_blocked_tld_filter(settings: Settings) -> BaseUrlFilter:
    blocked_tlds = settings.friend_link_tld_blocklist or BlockedTldFilter().blocked_tlds
    return BlockedTldFilter(blocked_tlds=blocked_tlds)


def _build_model_consensus_filter(settings: Settings) -> BaseUrlFilter:
    return ModelConsensusFilter(model_root=settings.decision_model_root)


FILTER_REGISTRY: dict[str, FilterFactory] = {
    "non_http_scheme": _static_filter_factory(NonHttpSchemeFilter),
    "same_domain": _static_filter_factory(SameDomainFilter),
    "exact_url_blocklist": _settings_value_filter_factory(
        ExactUrlBlocklistFilter,
        setting_attr="friend_link_exact_url_blocklist",
        constructor_kwarg="exact_url_blocklist",
    ),
    "prefix_blocklist": _settings_value_filter_factory(
        PrefixBlocklistFilter,
        setting_attr="friend_link_prefix_blocklist",
        constructor_kwarg="prefix_blocklist",
    ),
    "platform_domain": _static_filter_factory(PlatformDomainFilter),
    "custom_domain_blocklist": _settings_value_filter_factory(
        CustomDomainBlocklistFilter,
        setting_attr="friend_link_domain_blocklist",
        constructor_kwarg="domain_blocklist",
    ),
    "blocked_tld": _build_blocked_tld_filter,
    "root_path": _static_filter_factory(RootPathFilter),
    "location_fragment": _static_filter_factory(LocationFragmentFilter),
    "asset_suffix": _static_filter_factory(AssetSuffixFilter),
    "blocked_path": _static_filter_factory(BlockedPathFilter),
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
