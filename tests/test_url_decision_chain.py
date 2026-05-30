"""Tests for the configurable URL decision chain ordering and statuses."""

from __future__ import annotations

from pathlib import Path

from crawler.crawling.decisions.base import UrlCandidateContext
from crawler.crawling.decisions.chain import DEFAULT_FILTER_KINDS
from crawler.crawling.decisions.chain import build_url_decision_chain
from shared.config import Settings


def _settings(tmp_path: Path) -> Settings:
    """Build minimal settings whose filter-chain config falls back to defaults."""
    return Settings(
        db_path=tmp_path / "db.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        decision_model_root=tmp_path / "models",
        decision_model_consensus_enabled=False,
        filter_chain_config_path=tmp_path / "missing-filter-chain.toml",
    )


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
