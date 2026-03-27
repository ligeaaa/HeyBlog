"""Unit tests for crawler URL filtering rules."""

from app.crawler.filters import decide_blog_candidate
from app.crawler.filters import is_blog_candidate


def test_blog_candidate_rejects_self_domain() -> None:
    """Reject links on the same source domain."""
    assert not is_blog_candidate("https://blog.example.com/post", "blog.example.com")


def test_blog_candidate_rejects_known_platform() -> None:
    """Reject links pointing to known social/code platforms."""
    assert not is_blog_candidate("https://github.com/user/repo", "blog.example.com")


def test_blog_candidate_accepts_external_blog() -> None:
    """Accept external blog-like links."""
    assert is_blog_candidate("https://other-blog.example.net/", "blog.example.com")


def test_filter_rejects_blocked_suffixes_like_gov() -> None:
    """Reject blocked TLD categories such as government domains."""
    decision = decide_blog_candidate("https://agency.gov/", "blog.example.com")

    assert not decision.accepted
    assert decision.hard_blocked
    assert "blocked_tld" in decision.reasons


def test_filter_rejects_exact_url_and_prefix_blocklists() -> None:
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


def test_filter_accepts_positive_context_signal() -> None:
    """Accept links surfaced from a strong friend-link context."""
    decision = decide_blog_candidate(
        "https://friend.example/",
        "blog.example.com",
        link_text="Friend Blog",
        context_text="友情链接 邻居们",
    )

    assert decision.accepted
    assert "positive_context" in decision.reasons


def test_filter_hard_blocks_override_context() -> None:
    """Hard blocks should win even when the textual context looks positive."""
    decision = decide_blog_candidate(
        "https://github.com/example",
        "blog.example.com",
        link_text="Friend Blog",
        context_text="友情链接",
    )

    assert not decision.accepted
    assert decision.hard_blocked
