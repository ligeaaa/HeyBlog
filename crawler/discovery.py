"""Discover likely friend-link pages from a blog homepage."""

from __future__ import annotations

from urllib.parse import urljoin
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from bs4 import Tag

from crawler.utils import clean_text
from crawler.utils import text_contains_any
from crawler.utils import unique_in_order


PAGE_KEYWORDS = (
    "友链",
    "友情链接",
    "blogroll",
    "friend links",
    "friends",
    "links",
    "伙伴",
    "小伙伴",
    "邻居",
    "neighbors",
    "neighbours",
    "朋友",
    "友人",
    "friend",
)
NEGATIVE_KEYWORDS = (
    "about",
    "archive",
    "archives",
    "contact",
    "feed",
    "github",
    "rss",
    "search",
    "sitemap",
    "sponsor",
    "tag",
    "tags",
    "resource",
    "resources",
    "useful",
)
PATH_HINTS = ("/links", "/friends", "/friend-links", "/blogroll", "/friendlink")
CONTEXT_TAGS = {"nav", "aside", "footer", "section", "li", "div", "ul", "ol"}


def _anchor_context(anchor: Tag) -> str:
    """Collect nearby context text for an anchor."""
    fragments: list[str] = []
    current: Tag | None = anchor
    seen: set[str] = set()

    while current is not None:
        current = current.parent if isinstance(current.parent, Tag) else None
        if current is None or current.name not in CONTEXT_TAGS:
            continue
        text = clean_text(current.get_text(" ", strip=True))
        if not text or text in seen:
            continue
        seen.add(text)
        fragments.append(text)
        if len(fragments) >= 2:
            break

    return " ".join(fragments)


def _looks_like_friend_links_page(anchor: Tag) -> bool:
    """Return True when an anchor looks like a friend-link page entry."""
    href = anchor["href"].strip()
    anchor_text = clean_text(anchor.get_text(" ", strip=True))
    context_text = _anchor_context(anchor)
    combined = clean_text(f"{anchor_text} {context_text}")
    path = (urlparse(href).path or "/").lower()

    if not anchor_text and not context_text:
        return False

    # Prefer anchors whose label or nearby container speaks the language of a
    # friend-links directory, but reject generic "links/resources" navigation.
    if text_contains_any(combined, NEGATIVE_KEYWORDS):
        return False
    if text_contains_any(combined, PAGE_KEYWORDS):
        return True
    if any(hint in path for hint in PATH_HINTS):
        return True
    return False


def _candidate_page_urls(base_url: str, soup: BeautifulSoup) -> list[str]:
    """Return homepage-discovered friend-link page URLs."""
    urls = [
        urljoin(base_url, anchor["href"].strip())
        for anchor in soup.find_all("a", href=True)
        if _looks_like_friend_links_page(anchor)
    ]
    return unique_in_order(urls)


def _fallback_page_urls(base_url: str) -> list[str]:
    """Return deterministic fallback paths for blogs without clear homepage clues."""
    return unique_in_order(urljoin(base_url, hint) for hint in PATH_HINTS)


def discover_friend_links_pages(base_url: str, html: str) -> list[str]:
    """Infer friend-link page URLs from homepage anchors and fallback paths."""
    soup = BeautifulSoup(html, "html.parser")
    candidates = _candidate_page_urls(base_url, soup)

    if candidates:
        return candidates

    return _fallback_page_urls(base_url)
