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
    """Collect short nearby context text for one homepage anchor.

    Args:
        anchor: Anchor tag being evaluated as a possible friend-link page entry.

    Returns:
        A normalized string built from up to two nearby structural parents so
        keyword matching can use more than the anchor text alone.
    """
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
    """Decide whether one homepage anchor likely points to a friend-link page.

    Args:
        anchor: Anchor tag discovered on the blog homepage.

    Returns:
        ``True`` when the anchor text, nearby context, or path shape indicates a
        likely friend-link directory page.
    """
    href = anchor["href"].strip()
    anchor_text = clean_text(anchor.get_text(" ", strip=True))
    context_text = _anchor_context(anchor)
    combined = clean_text(f"{anchor_text} {context_text}")
    path = (urlparse(href).path or "/").lower()

    if not anchor_text and not context_text:
        return False
    if text_contains_any(combined, NEGATIVE_KEYWORDS):
        return False
    if text_contains_any(combined, PAGE_KEYWORDS):
        return True
    if any(hint in path for hint in PATH_HINTS):
        return True
    return False


def _candidate_page_urls(base_url: str, soup: BeautifulSoup) -> list[str]:
    """Collect candidate friend-link page URLs directly from homepage anchors.

    Args:
        base_url: Homepage URL used to resolve relative links.
        soup: Parsed homepage HTML tree.

    Returns:
        A de-duplicated list of absolute candidate page URLs in discovery order.
    """
    # Discovery deliberately stays homepage-only: it guesses which pages are
    # likely to contain friend links, but does not inspect their contents here.
    urls = [
        urljoin(base_url, anchor["href"].strip())
        for anchor in soup.find_all("a", href=True)
        if _looks_like_friend_links_page(anchor)
    ]
    return unique_in_order(urls)


def _fallback_page_urls(base_url: str) -> list[str]:
    """Generate deterministic fallback friend-link paths for one homepage.

    Args:
        base_url: Homepage URL used to resolve common friend-link path hints.

    Returns:
        A de-duplicated list of absolute fallback URLs derived from known common
        friend-link path patterns.
    """
    return unique_in_order(urljoin(base_url, hint) for hint in PATH_HINTS)


def discover_friend_links_pages(base_url: str, html: str) -> list[str]:
    """Infer friend-link directory pages from homepage HTML.

    Args:
        base_url: Homepage URL used to resolve relative anchors and fallback
            path hints.
        html: Homepage HTML source to inspect.

    Returns:
        A list of candidate friend-link page URLs, either discovered from page
        markup or synthesized from fallback path conventions.
    """
    soup = BeautifulSoup(html, "html.parser")
    candidates = _candidate_page_urls(base_url, soup)
    if candidates:
        return candidates
    # Fallback paths keep the crawler useful for blogs whose homepage exposes no
    # explicit friend-link anchor but follows common URL conventions.
    return _fallback_page_urls(base_url)
