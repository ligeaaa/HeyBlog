"""Extract candidate hyperlinks from crawled HTML pages."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from bs4 import Tag


SECTION_KEYWORDS = ("友链", "友情链接", "friends", "friend links", "blogroll", "neighbors")
NEGATIVE_SECTION_KEYWORDS = ("nav", "archive", "contact", "footer", "rss", "search")
STRUCTURAL_CONTAINERS = ("main", "section", "article", "aside", "div", "ul", "ol", "table")
MIN_SECTION_SCORE = 2.5


@dataclass(slots=True)
class ExtractedLink:
    """Represent one extracted anchor link with page context."""

    url: str
    text: str
    context_text: str = ""
    section_score: float = 0.0
    section_reason: str = ""


@dataclass(slots=True)
class SectionCandidate:
    """Represent a scored page section."""

    element_id: int
    score: float
    reason: str
    text: str


def _clean_text(value: str) -> str:
    """Normalize extracted text for section scoring."""
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


def _section_score(base_url: str, container: Tag, index: int) -> SectionCandidate | None:
    """Score one structural container as a friend-link section candidate."""
    text = _clean_text(container.get_text(" ", strip=True))
    if not text:
        return None

    heading = _heading_text(container)
    external_links = _count_external_links(base_url, container)
    anchors = container.find_all("a", href=True)
    score = 0.0
    reasons: list[str] = []

    if heading and any(keyword in heading.lower() for keyword in SECTION_KEYWORDS):
        score += 2.0
        reasons.append("heading_keyword")
    if any(keyword in text.lower() for keyword in SECTION_KEYWORDS):
        score += 1.0
        reasons.append("section_keyword")
    if any(keyword in text.lower() for keyword in NEGATIVE_SECTION_KEYWORDS):
        score -= 1.0
        reasons.append("negative_section_keyword")
    if external_links >= 3:
        score += 1.5
        reasons.append("external_link_density")
    if len(anchors) >= 4:
        score += 0.5
        reasons.append("anchor_density")

    classes = " ".join(container.get("class", []))
    identifier = str(container.get("id", ""))
    combined = f"{classes} {identifier}".lower()
    if combined and any(keyword in combined for keyword in SECTION_KEYWORDS):
        score += 1.0
        reasons.append("container_keyword")

    if container.name in {"ul", "ol", "table", "aside", "section"}:
        score += 0.5
        reasons.append(f"{container.name}_structure")

    if score <= 0:
        return None

    return SectionCandidate(
        element_id=index,
        score=score,
        reason=",".join(dict.fromkeys(reasons)),
        text=heading or text[:120],
    )


def select_candidate_sections(
    base_url: str,
    html: str,
    *,
    min_section_score: float = MIN_SECTION_SCORE,
) -> list[SectionCandidate]:
    """Return ranked section candidates for a candidate friend-link page."""
    soup = BeautifulSoup(html, "html.parser")
    sections: list[SectionCandidate] = []
    containers = soup.find_all(STRUCTURAL_CONTAINERS)

    for index, container in enumerate(containers):
        candidate = _section_score(base_url, container, index)
        if candidate is None or candidate.score < min_section_score:
            continue
        sections.append(candidate)

    return sorted(sections, key=lambda item: (item.score, item.element_id), reverse=True)


def extract_candidate_links(
    base_url: str,
    html: str,
    *,
    page_confidence: float = 0.0,
    min_section_score: float = MIN_SECTION_SCORE,
) -> list[ExtractedLink]:
    """Parse HTML and return absolute links from the highest-scoring sections."""
    soup = BeautifulSoup(html, "html.parser")
    containers = soup.find_all(STRUCTURAL_CONTAINERS)
    selected = {
        candidate.element_id: candidate
        for candidate in select_candidate_sections(
            base_url,
            html,
            min_section_score=min_section_score,
        )[:2]
    }

    if not selected and page_confidence >= 3.0:
        selected = {
            index: SectionCandidate(
                element_id=index,
                score=page_confidence,
                reason="whole_page_fallback",
                text="whole_page_fallback",
            )
            for index, _ in enumerate(containers[:1])
        }

    links: list[ExtractedLink] = []
    seen_urls: set[str] = set()
    for index, container in enumerate(containers):
        section = selected.get(index)
        if section is None:
            continue
        section_text = _clean_text(container.get_text(" ", strip=True))
        for anchor in container.find_all("a", href=True):
            url = urljoin(base_url, anchor["href"].strip())
            if url in seen_urls:
                continue
            seen_urls.add(url)
            links.append(
                ExtractedLink(
                    url=url,
                    text=_clean_text(anchor.get_text(" ", strip=True)),
                    context_text=section_text[:240],
                    section_score=section.score,
                    section_reason=section.reason,
                )
            )
    return links
