"""Unit tests for URL normalization behavior."""

from crawler.crawling.normalization import normalize_url
from crawler.crawling.normalization import resolve_blog_identity


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
    assert www.canonical_url == "https://langhai.cc/"
    assert blog.canonical_url == "https://langhai.cc/"
    assert "www_alias_collapsed" in www.reason_codes
    assert "blog_alias_collapsed" in blog.reason_codes
    assert "default_homepage_path_collapsed" in blog.reason_codes


def test_resolve_blog_identity_collapses_tenant_like_homepage_subdomains_to_root() -> None:
    """Tenant-like homepage subdomains should share one registrable-root identity and URL."""
    first = resolve_blog_identity("https://zhuruilei.66law.cn/")
    second = resolve_blog_identity("https://lichenlvs.66law.cn/")
    root = resolve_blog_identity("https://66law.cn/")

    assert first.identity_key == "site:66law.cn/"
    assert second.identity_key == first.identity_key
    assert root.identity_key == first.identity_key
    assert first.canonical_url == "https://66law.cn/"
    assert second.canonical_url == "https://66law.cn/"
    assert "tenant_subdomain_collapsed" in first.reason_codes
    assert "tenant_subdomain_collapsed" in second.reason_codes


def test_resolve_blog_identity_keeps_short_non_reserved_subdomains_distinct() -> None:
    """Short subdomains should not be auto-collapsed into the registrable root."""
    short = resolve_blog_identity("https://team.example.com/")

    assert short.identity_key == "site:team.example.com/"
    assert short.canonical_url == "https://team.example.com/"


def test_resolve_blog_identity_keeps_github_io_sites_distinct() -> None:
    """github.io sites are user-owned homes and must not be collapsed to the shared host root."""
    site = resolve_blog_identity("https://verylongusername.github.io/")

    assert site.identity_key == "site:verylongusername.github.io/"
    assert site.canonical_url == "https://verylongusername.github.io/"
    assert "tenant_subdomain_collapsed" not in site.reason_codes


def test_resolve_blog_identity_keeps_gitee_io_sites_distinct() -> None:
    """gitee.io sites are user-owned homes and must not be collapsed to the shared host root."""
    site = resolve_blog_identity("https://verylongusername.gitee.io/")

    assert site.identity_key == "site:verylongusername.gitee.io/"
    assert site.canonical_url == "https://verylongusername.gitee.io/"
    assert "tenant_subdomain_collapsed" not in site.reason_codes
