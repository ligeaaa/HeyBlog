"""Unit tests for the optional classifier adapter."""

import pytest

from app.config import Settings
from app.crawler.classifier import ClassifierUnavailableError
from app.crawler.classifier import build_classifier


def build_settings(tmp_path, *, enable_mcp_classifier: bool = False) -> Settings:
    """Create isolated settings for classifier tests."""
    return Settings(
        db_path=tmp_path / "db.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        enable_mcp_classifier=enable_mcp_classifier,
    )


def test_build_classifier_disabled_by_default(tmp_path) -> None:
    """The classifier adapter should be absent unless explicitly enabled."""
    settings = build_settings(tmp_path)

    assert build_classifier(settings) is None


def test_classifier_cache_key_depends_on_url_and_body(tmp_path) -> None:
    """Cache keys should change when either URL or content changes."""
    classifier = build_classifier(build_settings(tmp_path, enable_mcp_classifier=True))
    assert classifier is not None

    first = classifier.build_cache_key("https://example.com/links", "<html>one</html>")
    second = classifier.build_cache_key("https://example.com/links", "<html>two</html>")

    assert first != second


def test_classifier_review_raises_when_not_configured(tmp_path) -> None:
    """Enabled adapter still fails closed until a remote MCP implementation exists."""
    classifier = build_classifier(build_settings(tmp_path, enable_mcp_classifier=True))
    assert classifier is not None

    with pytest.raises(ClassifierUnavailableError):
        classifier.review_links("https://example.com/links", "<html></html>", [])
