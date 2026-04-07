"""Unit tests for URL normalization behavior."""

from crawler.normalizer import normalize_url
from crawler.normalizer import resolve_blog_identity


def test_normalize_url_removes_tracking_params_and_fragment() -> None:
    """Strip tracking query params and hash fragments from URLs."""
    result = normalize_url("https://Example.com/blog/?utm_source=x&ref=y#section")
    assert result.normalized_url == "https://example.com/blog"
    assert result.domain == "example.com"


def test_resolve_blog_identity_collapses_safe_homepage_aliases() -> None:
    """Identity resolution should ignore scheme and safe homepage aliases."""
    root = resolve_blog_identity("https://langhai.cc")
    www = resolve_blog_identity("http://www.langhai.cc/")
    blog = resolve_blog_identity("http://blog.langhai.cc/index.html")
    docs = resolve_blog_identity("https://docs.langhai.cc/")

    assert root.identity_key == "site:langhai.cc/"
    assert www.identity_key == root.identity_key
    assert blog.identity_key == root.identity_key
    assert docs.identity_key == "site:docs.langhai.cc/"
    assert "www_alias_collapsed" in www.reason_codes
    assert "blog_alias_collapsed" in blog.reason_codes
    assert "default_homepage_path_collapsed" in blog.reason_codes
