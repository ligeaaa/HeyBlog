"""Configurable URL filter-chain loading and compatibility helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any

from crawler.crawling.decisions.base import BaseUrlFilter
from crawler.crawling.decisions.base import DECIDER_ROLE_RULE
from crawler.crawling.decisions.base import DECIDER_ROLE_SUCCESS
from crawler.crawling.decisions.base import FilterDecision
from crawler.crawling.decisions.base import UrlCandidateContext
from crawler.crawling.decisions.consensus import ModelConsensusFilter
from crawler.crawling.decisions.filters import AssetSuffixFilter
from crawler.crawling.decisions.filters import BlockedPathFilter
from crawler.crawling.decisions.filters import BlockedTldFilter
from crawler.crawling.decisions.filters import CustomDomainBlocklistFilter
from crawler.crawling.decisions.filters import DuplicateUrlFilter
from crawler.crawling.decisions.filters import ExactUrlBlocklistFilter
from crawler.crawling.decisions.filters import LocationFragmentFilter
from crawler.crawling.decisions.filters import NonHttpSchemeFilter
from crawler.crawling.decisions.filters import PlatformDomainFilter
from crawler.crawling.decisions.filters import PrefixBlocklistFilter
from crawler.crawling.decisions.filters import RootPathFilter
from crawler.crawling.decisions.filters import SameDomainFilter
from crawler.crawling.decisions.rss import RssDiscoveryFilter
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
    return ModelConsensusFilter(
        model_root=settings.decision_model_root,
        model_api_base_url=settings.model_api_base_url,
        strategy=settings.decision_model_consensus_strategy,
        consensus_threshold=settings.decision_model_consensus_threshold,
    )


def _build_rss_discovery_filter(settings: Settings) -> BaseUrlFilter:
    del settings
    return RssDiscoveryFilter()


def _build_implicit_success_deciders(
    settings: Settings,
    *,
    configured_filter_kinds: set[str],
    disabled_filter_kinds: set[str],
) -> list[BaseUrlFilter]:
    """Append optional success deciders controlled only by settings toggles.

    Args:
        settings: Runtime settings that enable or disable optional deciders.
        configured_filter_kinds: Filter kinds mentioned by the TOML config.
        disabled_filter_kinds: Filter kinds explicitly disabled in the TOML
            config.

    Returns:
        Success decider filters that should be appended after deterministic
        rule filters because the config omitted them and the corresponding
        runtime toggle is enabled.
    """
    implicit_filters: list[BaseUrlFilter] = []
    if (
        settings.rss_discovery_enabled
        and "rss_discovery" not in configured_filter_kinds
        and "rss_discovery" not in disabled_filter_kinds
    ):
        implicit_filters.append(_build_rss_discovery_filter(settings))
    if (
        settings.decision_model_consensus_enabled
        and "model_consensus" not in configured_filter_kinds
        and "model_consensus" not in disabled_filter_kinds
    ):
        implicit_filters.append(_build_model_consensus_filter(settings))
    return implicit_filters


FILTER_REGISTRY: dict[str, FilterFactory] = {
    "duplicate_url": _static_filter_factory(DuplicateUrlFilter),
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
    "rss_discovery": _build_rss_discovery_filter,
    "model_consensus": _build_model_consensus_filter,
}

DEFAULT_FILTER_KINDS = (
    "duplicate_url",
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
    "rss_discovery",
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
        configured_filter_kinds: set[str] = set()
        disabled_filter_kinds: set[str] = set()
        for item in _load_filter_chain_config(settings.filter_chain_config_path):
            kind = str(item.get("kind", "")).strip()
            if kind:
                configured_filter_kinds.add(kind)
            if not bool(item.get("enabled", True)):
                if kind:
                    disabled_filter_kinds.add(kind)
                continue
            if kind == "model_consensus" and not settings.decision_model_consensus_enabled:
                continue
            if kind == "rss_discovery" and not settings.rss_discovery_enabled:
                continue
            factory = FILTER_REGISTRY.get(kind)
            if factory is None:
                raise ValueError(f"unknown_filter_kind:{kind}")
            loaded_filters.append(factory(settings))
        loaded_filters.extend(
            _build_implicit_success_deciders(
                settings,
                configured_filter_kinds=configured_filter_kinds,
                disabled_filter_kinds=disabled_filter_kinds,
            )
        )
        return cls(filters=tuple(loaded_filters))

    @property
    def rule_filters(self) -> tuple[BaseUrlFilter, ...]:
        """Return the mandatory deterministic rule filters (the AND-gate)."""
        return tuple(f for f in self.filters if getattr(f, "decider_role", DECIDER_ROLE_RULE) == DECIDER_ROLE_RULE)

    @property
    def success_deciders(self) -> tuple[BaseUrlFilter, ...]:
        """Return the success deciders evaluated as an ordered OR-group."""
        return tuple(f for f in self.filters if getattr(f, "decider_role", DECIDER_ROLE_RULE) == DECIDER_ROLE_SUCCESS)

    def evaluate(self, candidate: UrlCandidateContext) -> FilterDecision:
        """Evaluate the rule AND-gate then the success OR-group.

        Semantics:
            * Every ``rule`` filter must accept; the first rejection terminates
              evaluation and is returned verbatim.
            * The ``success`` deciders then run in order. The first decider that
              *confirms* the candidate keeps it immediately (carrying any
              discovered ``feed_url``). A decider that abstains (accepts without
              confirming) defers to the next decider. If no decider confirms and
              at least one positively rejected, the last rejection is returned;
              otherwise the candidate is kept.
        """
        for url_filter in self.rule_filters:
            decision = url_filter.apply(candidate)
            if not decision.accepted:
                return decision

        last_rejection: FilterDecision | None = None
        for decider in self.success_deciders:
            decision = decider.apply(candidate)
            if decision.confirmed:
                return FilterDecision(
                    accepted=True,
                    status="success",
                    confirmed=True,
                    feed_url=decision.feed_url,
                    accepted_by=decision.accepted_by,
                )
            if not decision.accepted:
                last_rejection = decision
        if last_rejection is not None:
            return last_rejection
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
        decision = self.evaluate(
            UrlCandidateContext(
                source_blog_id=0,
                source_domain=source_domain,
                normalized_url=normalize_url(url).normalized_url,
                link_text=link_text,
                context_text=context_text,
            )
        )
        if decision.accepted:
            return DecisionOutcome(accepted=True, score=0.0, reasons=("passed_filter_chain",))
        _, _, reason = str(decision.status).partition(":")
        return DecisionOutcome(accepted=False, score=0.0, reasons=(reason or "filter_rejected",), hard_blocked=True)


def build_url_decision_chain(settings: Settings) -> ConfiguredUrlFilterChain:
    """Build the configured URL filter chain used by crawler and rescans."""
    return ConfiguredUrlFilterChain.from_settings(settings)
