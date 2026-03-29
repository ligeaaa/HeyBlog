"""Unit tests for crawler URL filtering rules."""

from crawler.filters import decide_blog_candidate
from crawler.filters import is_blog_candidate


def test_filter_rejects_same_domain_links() -> None:
    """Reject links on the same source domain."""
    assert not is_blog_candidate("https://blog.example.com/post", "blog.example.com")


def test_filter_rejects_known_platform_domains() -> None:
    """Reject links pointing to known social/code platforms."""
    assert not is_blog_candidate("https://github.com/user/repo", "blog.example.com")


def test_filter_rejects_blocked_tlds_like_gov() -> None:
    """Reject blocked TLD categories such as government domains."""
    decision = decide_blog_candidate("https://agency.gov/", "blog.example.com")

    assert not decision.accepted
    assert decision.hard_blocked
    assert "blocked_tld" in decision.reasons


def test_filter_rejects_exact_url_and_prefix_blocklist_entries() -> None:
    """Reject exact URL and prefix-based blocks deterministically."""
    exact = decide_blog_candidate(
        "https://bad.example/",
        "blog.example.com",
        exact_url_blocklist=("https://bad.example",),
    )
    prefix = decide_blog_candidate(
        "https://ads.example/banner",
        "blog.example.com",
        prefix_blocklist=("https://ads.example",),
    )

    assert not exact.accepted
    assert not prefix.accepted


def test_filter_rejects_asset_suffixes_and_blocked_paths() -> None:
    """Reject assets and obvious non-homepage paths before soft scoring."""
    asset = decide_blog_candidate("https://friend.example/banner.png", "blog.example.com")
    blocked_path = decide_blog_candidate("https://friend.example/archive", "blog.example.com")

    assert not asset.accepted
    assert asset.hard_blocked
    assert "asset_suffix" in asset.reasons
    assert not blocked_path.accepted
    assert blocked_path.hard_blocked
    assert "blocked_path" in blocked_path.reasons


def test_filter_accepts_blog_like_links_with_positive_context() -> None:
    """Accept links surfaced from a strong friend-link context."""
    decision = decide_blog_candidate(
        "https://friend.example/",
        "blog.example.com",
        link_text="Friend Blog",
        context_text="友情链接 邻居们",
    )

    assert decision.accepted
    assert "positive_context" in decision.reasons


def test_filter_keeps_hard_blocks_authoritative() -> None:
    """Hard blocks should win even when the textual context looks positive."""
    decision = decide_blog_candidate(
        "https://github.com/example",
        "blog.example.com",
        link_text="Friend Blog",
        context_text="友情链接",
    )

    assert not decision.accepted
    assert decision.hard_blocked


def test_filter_accepts_external_blog_without_extra_context() -> None:
    """External blog homepages can pass after hard blocks even without extra text."""
    assert is_blog_candidate("https://other-blog.example.net/", "blog.example.com")
