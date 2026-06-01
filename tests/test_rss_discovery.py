"""Tests for the RSS/Atom feed discovery success decider."""

from __future__ import annotations

from crawler.crawling.decisions.base import UrlCandidateContext
from crawler.crawling.decisions.rss import RssDiscoveryFilter
from crawler.crawling.fetching.base import FetchResult


VALID_RSS = (
    '<?xml version="1.0"?><rss version="2.0"><channel>'
    "<title>My Blog</title><item><title>Post 1</title></item>"
    "</channel></rss>"
)
VALID_ATOM = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom Blog</title>'
    "<entry><title>Entry 1</title></entry></feed>"
)
HOMEPAGE_WITH_RSS_LINK = (
    '<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml">'
    "</head><body>hi</body></html>"
)
HOMEPAGE_WITH_RELATIVE_ATOM_LINK = (
    '<html><head><link rel="alternate" type="application/atom+xml" href="atom/">'
    "</head><body>hi</body></html>"
)
HOMEPAGE_PLAIN = "<html><head><title>plain</title></head><body>no feed here</body></html>"


class StubFetcher:
    """Return canned responses for known URLs and fail for everything else."""

    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def fetch(self, url: str, *, timeout_seconds: float | None = None) -> FetchResult:
        self.calls.append(url)
        if url in self.pages:
            return FetchResult(url=url, status_code=200, text=self.pages[url])
        raise RuntimeError(f"404 {url}")

    def fetch_many(self, urls, *, max_concurrency, timeout_seconds=None):  # pragma: no cover - unused
        raise NotImplementedError


def _candidate(url: str, *, fetcher=None, deadline=None) -> UrlCandidateContext:
    return UrlCandidateContext(
        source_blog_id=1,
        source_domain="source.example.com",
        normalized_url=url,
        fetcher=fetcher,
        fetch_deadline=deadline,
    )


def test_rss_confirms_when_homepage_declares_valid_feed_link() -> None:
    """A declared <link rel=alternate> feed that parses should confirm the blog."""
    fetcher = StubFetcher(
        {
            "https://blog.example.com/": HOMEPAGE_WITH_RSS_LINK,
            "https://blog.example.com/feed.xml": VALID_RSS,
        }
    )
    decision = RssDiscoveryFilter().apply(_candidate("https://blog.example.com/", fetcher=fetcher))

    assert decision.confirmed is True
    assert decision.status == "success"
    assert decision.feed_url == "https://blog.example.com/feed.xml"


def test_rss_resolves_relative_declared_feed_link() -> None:
    """A relative declared feed href should resolve against the homepage URL."""
    fetcher = StubFetcher(
        {
            "https://blog.example.com/": HOMEPAGE_WITH_RELATIVE_ATOM_LINK,
            "https://blog.example.com/atom/": VALID_ATOM,
        }
    )
    decision = RssDiscoveryFilter().apply(_candidate("https://blog.example.com/", fetcher=fetcher))

    assert decision.confirmed is True
    assert decision.feed_url == "https://blog.example.com/atom/"


def test_rss_confirms_via_common_path_probe_when_no_link_declared() -> None:
    """When the homepage declares no feed, probing common paths should find one."""
    fetcher = StubFetcher(
        {
            "https://blog.example.com/": HOMEPAGE_PLAIN,
            "https://blog.example.com/feed": VALID_RSS,
        }
    )
    decision = RssDiscoveryFilter().apply(_candidate("https://blog.example.com/", fetcher=fetcher))

    assert decision.confirmed is True
    assert decision.feed_url == "https://blog.example.com/feed"


def test_rss_abstains_when_no_feed_is_found() -> None:
    """No discoverable feed is an abstain (accept, not confirm), not a rejection."""
    fetcher = StubFetcher({"https://blog.example.com/": HOMEPAGE_PLAIN})
    decision = RssDiscoveryFilter().apply(_candidate("https://blog.example.com/", fetcher=fetcher))

    assert decision.accepted is True
    assert decision.confirmed is False
    assert decision.feed_url is None


def test_rss_abstains_when_probe_content_is_not_a_feed() -> None:
    """A 200 response that is not a parseable feed must not confirm."""
    fetcher = StubFetcher(
        {
            "https://blog.example.com/": HOMEPAGE_PLAIN,
            "https://blog.example.com/feed": HOMEPAGE_PLAIN,
        }
    )
    decision = RssDiscoveryFilter().apply(_candidate("https://blog.example.com/", fetcher=fetcher))

    assert decision.confirmed is False


def test_rss_abstains_when_no_fetcher_is_available() -> None:
    """Offline callers without a fetcher must skip RSS discovery cleanly."""
    decision = RssDiscoveryFilter().apply(_candidate("https://blog.example.com/"))

    assert decision.accepted is True
    assert decision.confirmed is False


def test_rss_abstains_when_fetch_deadline_has_passed() -> None:
    """A passed crawl deadline should skip network work and abstain."""
    fetcher = StubFetcher(
        {
            "https://blog.example.com/": HOMEPAGE_WITH_RSS_LINK,
            "https://blog.example.com/feed.xml": VALID_RSS,
        }
    )
    decision = RssDiscoveryFilter().apply(
        _candidate("https://blog.example.com/", fetcher=fetcher, deadline=0.0)
    )

    assert decision.confirmed is False
    assert fetcher.calls == []


def test_rss_abstains_when_homepage_fetch_fails() -> None:
    """A homepage fetch failure should abstain rather than raise."""
    fetcher = StubFetcher({})
    decision = RssDiscoveryFilter().apply(_candidate("https://blog.example.com/", fetcher=fetcher))

    assert decision.accepted is True
    assert decision.confirmed is False
