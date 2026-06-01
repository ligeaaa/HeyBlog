"""RSS/Atom feed discovery as a success decider in the URL filter chain."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
import logging
from urllib.parse import urljoin
from urllib.parse import urlparse
from urllib.parse import urlunparse

from bs4 import BeautifulSoup
from bs4 import Tag

from crawler.crawling.decisions.base import DECIDER_ROLE_SUCCESS
from crawler.crawling.decisions.base import FilterDecision
from crawler.crawling.decisions.base import StaticStatusUrlFilter
from crawler.crawling.decisions.base import UrlCandidateContext
from crawler.crawling.fetching.base import FetchResult
from shared.observability import get_logger
from shared.observability import log_event

LOGGER = get_logger(__name__)

# Feed MIME types declared on <link rel="alternate"> tags.
FEED_LINK_TYPES = frozenset(
    {
        "application/rss+xml",
        "application/atom+xml",
        "application/feed+json",
        "application/json",
    }
)
# Fallback feed paths probed when the homepage does not declare a feed link.
COMMON_FEED_PATHS = (
    "/feed",
    "/feed/",
    "/rss",
    "/rss.xml",
    "/atom.xml",
    "/feed.xml",
    "/index.xml",
)


def _is_valid_feed(content: str) -> bool:
    """Return whether fetched content parses as a non-empty RSS/Atom feed.

    Args:
        content: Raw response body fetched from a candidate feed URL.

    Returns:
        ``True`` when ``feedparser`` recognizes a feed version and the document
        carries either a feed title or at least one entry.
    """
    if not content.strip():
        return False
    import feedparser

    parsed = feedparser.parse(content)
    # ``version`` is empty for documents feedparser does not recognize as a
    # feed; ``bozo`` alone is too strict because many real feeds are slightly
    # malformed yet still parse into usable entries.
    if not parsed.get("version"):
        return False
    has_entries = bool(parsed.get("entries"))
    has_title = bool(parsed.get("feed", {}).get("title"))
    return has_entries or has_title


@dataclass(slots=True)
class RssDiscoveryFilter(StaticStatusUrlFilter):
    """Confirm a candidate as a blog when it exposes a valid RSS/Atom feed.

    This is a ``success`` decider: it runs after the deterministic rule
    AND-gate. A confirmed feed keeps the candidate immediately (and records the
    feed URL); the absence of a feed is an abstain, not a rejection, so the
    candidate falls through to the next success decider (model consensus).

    Attributes:
        max_path_probes: Maximum number of fallback feed paths probed when the
            homepage declares no feed link.
        kind: Registry/config key for this decider.
        filter_kind: Status namespace used in funnel statistics.
        filter_reason: Status suffix emitted when the decider confirms a feed.
        decider_role: Marks this filter as part of the success OR-group.
    """

    max_path_probes: int = len(COMMON_FEED_PATHS)
    kind: str = field(init=False, default="rss_discovery")
    filter_kind: str = field(init=False, default="rss")
    filter_reason: str = field(init=False, default="rss_feed_found")
    decider_role: str = field(init=False, default=DECIDER_ROLE_SUCCESS)

    def apply(self, candidate: UrlCandidateContext) -> FilterDecision:
        """Confirm the candidate when a valid feed is discovered, else abstain.

        Args:
            candidate: Normalized candidate carrying the optional live fetcher
                and per-blog fetch deadline.

        Returns:
            A confirmed decision (with ``feed_url``) when a valid feed exists,
            otherwise an abstain decision so later deciders can run.
        """
        fetcher = candidate.fetcher
        if fetcher is None:
            # Offline callers (dedup scan, funnel stats) have no fetcher; the
            # network-bound decider abstains so it never blocks those paths.
            return self.accept()
        if self._deadline_passed(candidate):
            return self.accept()

        feed_url = self._discover_feed(candidate, fetcher)
        if feed_url is None:
            return self.accept()
        return self.confirm(feed_url=feed_url, accepted_by="rss")

    def _deadline_passed(self, candidate: UrlCandidateContext) -> bool:
        """Return whether the per-blog fetch budget is already exhausted."""
        if candidate.fetch_deadline is None:
            return False
        from time import monotonic

        return monotonic() >= candidate.fetch_deadline

    def _fetch(self, fetcher: object, url: str) -> FetchResult | None:
        """Fetch one URL defensively, returning ``None`` on any failure."""
        try:
            return fetcher.fetch(url)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            # Feed discovery is best-effort; a single failed request must not
            # break the surrounding crawl. Any failure just means "no feed".
            log_event(
                LOGGER,
                event="rss.discovery.fetch_failed",
                message="rss feed discovery fetch failed",
                level=logging.DEBUG,
                stage="rss_discovery",
                target_url=url,
                error_type=type(exc).__name__,
            )
            return None

    def _discover_feed(self, candidate: UrlCandidateContext, fetcher: object) -> str | None:
        """Discover a valid feed for the candidate homepage.

        Args:
            candidate: Candidate context whose normalized URL is the homepage.
            fetcher: Live HTTP fetcher used to retrieve homepage and feeds.

        Returns:
            The validated feed URL, or ``None`` when no usable feed is found.
        """
        homepage_url = candidate.normalized_url
        homepage = self._fetch(fetcher, homepage_url)

        declared_feeds: list[str] = []
        if homepage is not None:
            page_url = homepage.url or homepage_url
            declared_feeds = _declared_feed_urls(page_url, homepage.text)
            # A declared feed may itself be a valid feed document; validate it.
            for declared in declared_feeds:
                if self._validate_feed_url(fetcher, declared):
                    return declared

        # Fall back to probing common feed paths relative to the homepage origin.
        for probe_url in self._probe_urls(homepage_url):
            if probe_url in declared_feeds:
                continue
            if self._validate_feed_url(fetcher, probe_url):
                return probe_url
        return None

    def _validate_feed_url(self, fetcher: object, feed_url: str) -> bool:
        """Fetch one feed URL and confirm it parses as a valid feed."""
        result = self._fetch(fetcher, feed_url)
        if result is None:
            return False
        return _is_valid_feed(result.text)

    def _probe_urls(self, homepage_url: str) -> list[str]:
        """Return absolute fallback feed URLs derived from the homepage origin."""
        parsed = urlparse(homepage_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return []
        origin = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
        return [urljoin(origin + "/", path.lstrip("/")) for path in COMMON_FEED_PATHS[: self.max_path_probes]]


def _declared_feed_urls(page_url: str, html: str) -> list[str]:
    """Extract feed URLs declared via ``<link rel="alternate">`` tags.

    Args:
        page_url: Final fetched homepage URL used to resolve relative hrefs.
        html: Raw homepage HTML to parse.

    Returns:
        Ordered, de-duplicated absolute feed URLs declared by the homepage.
    """
    soup = BeautifulSoup(html, "html.parser")
    feeds: list[str] = []
    seen: set[str] = set()
    for link in soup.find_all("link", href=True):
        if not isinstance(link, Tag):
            continue
        if not _is_feed_link(link):
            continue
        href = str(link.get("href", "")).strip()
        if not href:
            continue
        resolved = urljoin(page_url, href)
        if resolved in seen:
            continue
        seen.add(resolved)
        feeds.append(resolved)
    return feeds


def _is_feed_link(link: Tag) -> bool:
    """Return whether one ``<link>`` tag advertises a feed alternate."""
    rel_value = link.get("rel")
    if isinstance(rel_value, str):
        rel_tokens = {token.strip().lower() for token in rel_value.split() if token.strip()}
    elif isinstance(rel_value, list):
        rel_tokens = {str(token).strip().lower() for token in rel_value if str(token).strip()}
    else:
        rel_tokens = set()
    if "alternate" not in rel_tokens:
        return False
    link_type = str(link.get("type", "")).strip().lower()
    return link_type in FEED_LINK_TYPES
