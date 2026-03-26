"""Unit tests for URL normalization behavior."""

from app.crawler.normalizer import normalize_url


def test_normalize_url_removes_tracking_params_and_fragment() -> None:
    """Strip tracking query params and hash fragments from URLs."""
    result = normalize_url("https://Example.com/blog/?utm_source=x&ref=y#section")
    assert result.normalized_url == "https://example.com/blog"
    assert result.domain == "example.com"
