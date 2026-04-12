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
    """Represent one extracted anchor candidate from a friend-link section.

    Attributes:
        url: Absolute URL resolved from the anchor's ``href``.
        text: Normalized anchor text shown to users on the page.
        context_text: Normalized local container text used later by filtering
            and diagnostics.
    """

    url: str
    text: str
    context_text: str = ""


def _container_depth(container: Tag) -> int:
    """Measure how deeply one HTML container is nested in the document tree.

    Args:
        container: Structural HTML container being considered as a section.

    Returns:
        An integer depth where higher values mean the container is more specific
        and usually preferable when multiple nested containers match.
    """
    depth = 0
    current = container.parent
    while isinstance(current, Tag):
        depth += 1
        current = current.parent
    return depth


def _count_external_links(base_url: str, container: Tag) -> int:
    """Count external-looking links inside one candidate section.

    Args:
        base_url: Page URL used to resolve relative anchors and identify the
            page's own host.
        container: Section candidate whose anchors should be counted.

    Returns:
        The number of anchors that resolve to non-empty external HTTP(S) hosts.
    """
    host = urlparse(base_url).netloc.lower()
    count = 0
    for anchor in container.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"].strip())
        parsed = urlparse(url)
        if parsed.scheme.startswith("http") and parsed.netloc.lower() and parsed.netloc.lower() != host:
            count += 1
    return count


def _heading_text(container: Tag) -> str:
    """Return the strongest local heading text for one section candidate.

    Args:
        container: HTML container that may represent a friend-links section.

    Returns:
        The most informative nearby heading text, or an empty string when no
        heading-like element is found.
    """
    heading = container.find(["h1", "h2", "h3", "h4", "legend", "summary", "strong"])
    if heading is not None:
        return clean_text(heading.get_text(" ", strip=True))
    if isinstance(container.previous_sibling, Tag):
        return clean_text(container.previous_sibling.get_text(" ", strip=True))
    return ""


def _looks_like_friend_links_section(base_url: str, container: Tag) -> bool:
    """Decide whether one container likely represents a friend-links section.

    Args:
        base_url: Page URL used to evaluate external links within the container.
        container: Structural HTML container being evaluated.

    Returns:
        ``True`` when section keywords, identifiers, or enough external links
        suggest the container is a friend-links area.
    """
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
    """Check whether one container overlaps an already selected section.

    Args:
        container: New candidate container being considered.
        chosen: Containers already selected for extraction.

    Returns:
        ``True`` when the candidate is nested inside or wraps an already chosen
        container and should therefore be skipped.
    """
    return any(existing in container.parents or container in existing.parents for existing in chosen)


def _select_candidate_containers(base_url: str, containers: list[Tag]) -> list[Tag]:
    """Pick the best HTML containers that look like friend-links sections.

    Args:
        base_url: Page URL used to evaluate external links in each container.
        containers: Structural HTML containers extracted from the page.

    Returns:
        A list of non-overlapping section containers ordered by specificity and
        original appearance.
    """
    matching: list[tuple[int, int, Tag]] = []
    for index, container in enumerate(containers):
        if not _looks_like_friend_links_section(base_url, container):
            continue
        matching.append((_container_depth(container), index, container))

    matching.sort(key=lambda item: (-item[0], item[1]))
    selected: list[Tag] = []
    for _, _, container in matching:
        # When nested containers all look plausible, keep the deepest one to
        # avoid extracting the same links from both a wrapper and its child list.
        if _is_overlapping_container(container, selected):
            continue
        selected.append(container)
    return selected


def _fallback_container(containers: list[Tag]) -> list[Tag]:
    """Choose a minimal fallback container when no explicit section matches.

    Args:
        containers: Structural HTML containers extracted from the page.

    Returns:
        A one-item list containing the first anchor-bearing structural container,
        or the first structural container when none contain anchors.
    """
    for container in containers:
        if container.find("a", href=True) is not None:
            return [container]
    return containers[:1]


def extract_candidate_links(base_url: str, html: str) -> list[ExtractedLink]:
    """Extract absolute candidate links from a friend-link-like page.

    Args:
        base_url: Page URL used to resolve relative links.
        html: Raw HTML source of the candidate friend-link page.

    Returns:
        A list of ``ExtractedLink`` objects representing unique anchors pulled
        from the selected friend-link containers.
    """
    soup = BeautifulSoup(html, "html.parser")
    containers = soup.find_all(STRUCTURAL_CONTAINERS)
    links: list[ExtractedLink] = []
    seen_urls: set[str] = set()

    selected = _select_candidate_containers(base_url, containers)
    if not selected:
        # Fallback extraction keeps the pipeline moving for unusual markup, while
        # the later filter stage still decides which targets are worth storing.
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
