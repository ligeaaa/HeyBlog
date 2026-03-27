"""Extract candidate hyperlinks from crawled HTML pages."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from bs4 import Tag


SECTION_KEYWORDS = ("友链", "友情链接", "friends", "friend links", "blogroll", "neighbors")
NEGATIVE_SECTION_KEYWORDS = ("archive", "contact", "rss", "search", "sitemap")
STRUCTURAL_CONTAINERS = ("main", "section", "article", "aside", "div", "ul", "ol", "table")


@dataclass(slots=True)
class ExtractedLink:
    """Represent one extracted anchor link with nearby context."""

    url: str
    text: str
    context_text: str = ""


def _clean_text(value: str) -> str:
    """Normalize extracted text for keyword matching."""
    return " ".join(value.split()).strip()


def _count_external_links(base_url: str, container: Tag) -> int:
    """Count outbound-looking links in a section."""
    host = urlparse(base_url).netloc.lower()
    count = 0
    for anchor in container.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"].strip())
        parsed = urlparse(url)
        if parsed.scheme.startswith("http") and parsed.netloc.lower() and parsed.netloc.lower() != host:
            count += 1
    return count


def _heading_text(container: Tag) -> str:
    """Return the strongest local heading for a section candidate."""
    heading = container.find(["h1", "h2", "h3", "h4", "legend", "summary", "strong"])
    if heading is not None:
        return _clean_text(heading.get_text(" ", strip=True))
    if isinstance(container.previous_sibling, Tag):
        return _clean_text(container.previous_sibling.get_text(" ", strip=True))
    return ""


def _looks_like_friend_links_section(base_url: str, container: Tag) -> bool:
    """Return True when a container likely holds friend links."""
    text = _clean_text(container.get_text(" ", strip=True))
    if not text:
        return False

    heading = _heading_text(container).lower()
    lowered = text.lower()
    classes = " ".join(container.get("class", [])).lower()
    identifier = str(container.get("id", "")).lower()
    combined = f"{classes} {identifier}"

    if any(keyword in lowered for keyword in NEGATIVE_SECTION_KEYWORDS):
        return False
    if any(keyword in heading for keyword in SECTION_KEYWORDS):
        return True
    if any(keyword in lowered for keyword in SECTION_KEYWORDS):
        return True
    if any(keyword in combined for keyword in SECTION_KEYWORDS):
        return True
    if _count_external_links(base_url, container) >= 3:
        return True
    return False


def extract_candidate_links(base_url: str, html: str) -> list[ExtractedLink]:
    """Parse HTML and return absolute links from friend-link-looking sections."""
    soup = BeautifulSoup(html, "html.parser")
    containers = soup.find_all(STRUCTURAL_CONTAINERS)
    links: list[ExtractedLink] = []
    seen_urls: set[str] = set()

    selected = [
        container for container in containers if _looks_like_friend_links_section(base_url, container)
    ]
    if not selected:
        selected = containers[:1]

    for container in selected:
        context_text = _clean_text(container.get_text(" ", strip=True))[:240]
        for anchor in container.find_all("a", href=True):
            url = urljoin(base_url, anchor["href"].strip())
            if url in seen_urls:
                continue
            seen_urls.add(url)
            links.append(
                ExtractedLink(
                    url=url,
                    text=_clean_text(anchor.get_text(" ", strip=True)),
                    context_text=context_text,
                )
            )
    return links
