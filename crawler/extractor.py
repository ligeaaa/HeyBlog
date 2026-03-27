"""Extract candidate hyperlinks from crawled HTML pages."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from bs4 import Tag

from crawler.utils import clean_text


SECTION_KEYWORDS = ("友链", "友情链接", "friends", "friend links", "blogroll", "neighbors")
NEGATIVE_SECTION_KEYWORDS = ("archive", "contact", "rss", "search", "sitemap")
STRUCTURAL_CONTAINERS = ("main", "section", "article", "aside", "div", "ul", "ol", "table")


@dataclass
class ExtractedLink:
    """Represent one extracted anchor link with nearby context."""

    url: str
    text: str
    context_text: str = ""


def _container_depth(container: Tag) -> int:
    """Measure how specific a container is within the page tree."""
    depth = 0
    current = container.parent
    while isinstance(current, Tag):
        depth += 1
        current = current.parent
    return depth


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
        return clean_text(heading.get_text(" ", strip=True))
    if isinstance(container.previous_sibling, Tag):
        return clean_text(container.previous_sibling.get_text(" ", strip=True))
    return ""


def _looks_like_friend_links_section(base_url: str, container: Tag) -> bool:
    """Return True when a container likely represents a friend-links section."""
    text = clean_text(container.get_text(" ", strip=True))
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

    external_links = _count_external_links(base_url, container)
    return external_links >= 3


def _is_overlapping_container(container: Tag, chosen: list[Tag]) -> bool:
    """Return True when the container overlaps an already selected section."""
    return any(existing in container.parents or container in existing.parents for existing in chosen)


def _select_candidate_containers(base_url: str, containers: list[Tag]) -> list[Tag]:
    """Pick the most specific containers that look like friend-links sections."""
    matching: list[tuple[int, int, Tag]] = []
    for index, container in enumerate(containers):
        if not _looks_like_friend_links_section(base_url, container):
            continue
        matching.append((_container_depth(container), index, container))

    # Prefer deeper containers so the extractor reads the most specific section first.
    matching.sort(key=lambda item: (-item[0], item[1]))
    selected: list[Tag] = []
    for _, _, container in matching:
        if _is_overlapping_container(container, selected):
            continue
        selected.append(container)
    return selected


def _fallback_container(containers: list[Tag]) -> list[Tag]:
    """Use the first structural container when no explicit section matches."""
    for container in containers:
        if container.find("a", href=True) is not None:
            return [container]
    return containers[:1]


def extract_candidate_links(base_url: str, html: str) -> list[ExtractedLink]:
    """Parse HTML and return absolute links from friend-link-looking sections."""
    soup = BeautifulSoup(html, "html.parser")
    containers = soup.find_all(STRUCTURAL_CONTAINERS)
    links: list[ExtractedLink] = []
    seen_urls: set[str] = set()

    # Extractor only decides where to read candidate anchors from; final keep/drop rules stay in filters.
    selected = _select_candidate_containers(base_url, containers)
    if not selected:
        selected = _fallback_container(containers)

    for container in selected:
        context_text = clean_text(container.get_text(" ", strip=True))[:240]
        for anchor in container.find_all("a", href=True):
            url = urljoin(base_url, anchor["href"].strip())
            if url in seen_urls:
                continue
            seen_urls.add(url)
            links.append(
                ExtractedLink(
                    url=url,
                    text=clean_text(anchor.get_text(" ", strip=True)),
                    context_text=context_text,
                )
            )
    return links
