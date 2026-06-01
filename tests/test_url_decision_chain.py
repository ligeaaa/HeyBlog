"""Tests for the configurable URL decision chain ordering and statuses."""

from __future__ import annotations

from pathlib import Path

from crawler.crawling.decisions.base import DECIDER_ROLE_SUCCESS
from crawler.crawling.decisions.base import FilterDecision
from crawler.crawling.decisions.base import UrlCandidateContext
from crawler.crawling.decisions.chain import ConfiguredUrlFilterChain
from crawler.crawling.decisions.chain import DEFAULT_FILTER_KINDS
from crawler.crawling.decisions.chain import build_url_decision_chain
from crawler.crawling.fetching.base import FetchResult
from shared.config import Settings


def _settings(tmp_path: Path, *, rss_enabled: bool = True) -> Settings:
    """Build minimal settings whose filter-chain config falls back to defaults."""
    return Settings(
        db_path=tmp_path / "db.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        decision_model_root=tmp_path / "models",
        decision_model_consensus_enabled=False,
        rss_discovery_enabled=rss_enabled,
        filter_chain_config_path=tmp_path / "missing-filter-chain.toml",
    )


class _RssStubFetcher:
    """Serve a homepage that declares a valid feed for one host only."""

    FEED = '<?xml version="1.0"?><rss version="2.0"><channel><title>T</title><item/></channel></rss>'
    HOME = '<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml"></head></html>'

    def fetch(self, url: str, *, timeout_seconds: float | None = None) -> FetchResult:
        if url.rstrip("/").endswith("feed.xml"):
            return FetchResult(url=url, status_code=200, text=self.FEED)
        return FetchResult(url=url, status_code=200, text=self.HOME)


class _RecordingSuccessDecider:
    """A success decider that records whether it was consulted."""

    kind = "recording"
    filter_kind = "model"
    filter_reason = "recorded_reject"
    decider_role = DECIDER_ROLE_SUCCESS

    def __init__(self) -> None:
        self.calls = 0

    def apply(self, candidate: UrlCandidateContext) -> FilterDecision:
        self.calls += 1
        return FilterDecision(accepted=False, status="model:recorded_reject")


def test_default_chain_leads_with_duplicate_url_step() -> None:
    """The duplicate-url accounting step should head the default ordering."""
    assert DEFAULT_FILTER_KINDS[0] == "duplicate_url"


def test_ordered_statuses_includes_duplicate_url_first(tmp_path: Path) -> None:
    """``ordered_statuses`` should expose ``rule:duplicate_url`` as the first key."""
    chain = build_url_decision_chain(_settings(tmp_path))

    statuses = chain.ordered_statuses()

    assert statuses[0] == "rule:duplicate_url"


def test_duplicate_url_filter_is_pass_through(tmp_path: Path) -> None:
    """The duplicate-url step always accepts; dedupe runs before the chain."""
    chain = build_url_decision_chain(_settings(tmp_path))
    duplicate_filter = chain.steps[0]

    decision = duplicate_filter.apply(
        UrlCandidateContext(
            source_blog_id=1,
            source_domain="source.example.com",
            normalized_url="https://friend.example/",
        )
    )

    assert duplicate_filter.kind == "duplicate_url"
    assert decision.accepted is True
    assert decision.status is None


def test_rss_discovery_precedes_model_consensus_in_defaults() -> None:
    """RSS discovery should be ordered before model consensus among success deciders."""
    assert "rss_discovery" in DEFAULT_FILTER_KINDS
    assert DEFAULT_FILTER_KINDS.index("rss_discovery") < DEFAULT_FILTER_KINDS.index("model_consensus")


def test_rss_discovery_disabled_removes_success_decider(tmp_path: Path) -> None:
    """Disabling RSS discovery should drop it from the loaded success deciders."""
    chain = build_url_decision_chain(_settings(tmp_path, rss_enabled=False))

    assert [f.kind for f in chain.success_deciders] == []


def test_rule_rejection_short_circuits_before_success_deciders(tmp_path: Path) -> None:
    """A failing rule filter should reject before any success decider runs."""
    recorder = _RecordingSuccessDecider()
    chain = build_url_decision_chain(_settings(tmp_path))
    chain = ConfiguredUrlFilterChain(filters=(*chain.rule_filters, recorder))

    decision = chain.evaluate(
        UrlCandidateContext(
            source_blog_id=1,
            source_domain="source.example.com",
            normalized_url="https://github.com/",
        )
    )

    assert decision.accepted is False
    assert decision.status == "rule:platform_blocked"
    assert recorder.calls == 0


def test_rss_confirmation_short_circuits_later_success_deciders(tmp_path: Path) -> None:
    """An RSS confirm should keep the candidate without consulting the model decider."""
    recorder = _RecordingSuccessDecider()
    chain = build_url_decision_chain(_settings(tmp_path))
    chain = ConfiguredUrlFilterChain(filters=(*chain.filters, recorder))

    decision = chain.evaluate(
        UrlCandidateContext(
            source_blog_id=1,
            source_domain="source.example.com",
            normalized_url="https://friend.example.com/",
            fetcher=_RssStubFetcher(),
        )
    )

    assert decision.accepted is True
    assert decision.confirmed is True
    assert decision.feed_url == "https://friend.example.com/feed.xml"
    assert recorder.calls == 0


def test_rss_abstain_falls_through_to_model_decider(tmp_path: Path) -> None:
    """When RSS finds no feed, the next success decider's rejection should win."""
    recorder = _RecordingSuccessDecider()
    chain = build_url_decision_chain(_settings(tmp_path))
    chain = ConfiguredUrlFilterChain(filters=(*chain.filters, recorder))

    decision = chain.evaluate(
        UrlCandidateContext(
            source_blog_id=1,
            source_domain="source.example.com",
            normalized_url="https://friend.example.com/",
            # No fetcher -> RSS abstains, so the recording decider must run.
        )
    )

    assert recorder.calls == 1
    assert decision.accepted is False
    assert decision.status == "model:recorded_reject"

