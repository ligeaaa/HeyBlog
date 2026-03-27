"""Discover likely friend-link pages from a blog homepage."""

from __future__ import annotations

from urllib.parse import urljoin
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from bs4 import Tag


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


def _clean_text(value: str) -> str:
    """Normalize extracted text for matching."""
    return " ".join(value.split()).strip()


def _text_contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    """Return True when the lower-cased text contains any provided keyword."""
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def _anchor_context(anchor: Tag) -> str:
    """Collect nearby context text for an anchor."""
    fragments: list[str] = []
    current: Tag | None = anchor
    seen: set[str] = set()

    while current is not None:
        current = current.parent if isinstance(current.parent, Tag) else None
        if current is None or current.name not in CONTEXT_TAGS:
            continue
        text = _clean_text(current.get_text(" ", strip=True))
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
    anchor_text = _clean_text(anchor.get_text(" ", strip=True))
    context_text = _anchor_context(anchor)
    combined = _clean_text(f"{anchor_text} {context_text}")
    path = (urlparse(href).path or "/").lower()

    if not anchor_text and not context_text:
        return False
    if _text_contains_any(combined, NEGATIVE_KEYWORDS):
        return False
    if _text_contains_any(combined, PAGE_KEYWORDS):
        return True
    if any(hint in path for hint in PATH_HINTS):
        return True
    return False


def discover_friend_links_pages(base_url: str, html: str) -> list[str]:
    """Infer friend-link page URLs from homepage anchors and fallback paths."""
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        if not _looks_like_friend_links_page(anchor):
            continue
        url = urljoin(base_url, anchor["href"].strip())
        if url in seen:
            continue
        seen.add(url)
        candidates.append(url)

    if candidates:
        return candidates

    for hint in PATH_HINTS:
        url = urljoin(base_url, hint)
        if url in seen:
            continue
        seen.add(url)
        candidates.append(url)
    return candidates
