"""Discover likely friend-link pages from a blog homepage."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from bs4 import Tag


STRONG_PAGE_KEYWORDS = (
    "友链",
    "友情链接",
    "blogroll",
    "friend links",
    "伙伴",
    "小伙伴",
    "邻居",
)
WEAK_PAGE_KEYWORDS = (
    "friends",
    "links",
    "neighbor",
    "neighbour",
    "neighbors",
    "neighbours",
)
PAGE_KEYWORDS = STRONG_PAGE_KEYWORDS + WEAK_PAGE_KEYWORDS
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
POSITIVE_CONTAINERS = {"nav", "aside", "footer", "section", "li"}
NEGATIVE_CONTAINERS = {"header"}
MIN_PAGE_SCORE = 2.5


@dataclass(slots=True)
class PageCandidate:
    """Represent a scored candidate friend-link page."""

    url: str
    score: float
    anchor_text: str
    context_text: str
    reasons: tuple[str, ...]

    def is_ambiguous(self, min_page_score: float = MIN_PAGE_SCORE) -> bool:
        """Return True when the candidate is neither clearly good nor clearly bad."""
        return self.score < min_page_score


def _clean_text(value: str) -> str:
    """Normalize extracted text for matching and diagnostics."""
    return " ".join(value.split()).strip()


def _text_contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    """Return True when the lower-cased text contains any provided keyword."""
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def _anchor_context(anchor: Tag) -> str:
    """Collect short nearby context for an anchor from useful ancestors."""
    fragments: list[str] = []
    current: Tag | None = anchor
    seen: set[str] = set()

    while current is not None:
        current = current.parent if isinstance(current.parent, Tag) else None
        if current is None:
            break
        if current.name not in POSITIVE_CONTAINERS | NEGATIVE_CONTAINERS | {"div", "ul", "ol"}:
            continue
        text = _clean_text(current.get_text(" ", strip=True))
        if not text or text in seen:
            continue
        seen.add(text)
        fragments.append(text)
        if len(fragments) >= 2:
            break

    return " ".join(fragments)


def _path_score(href: str) -> tuple[float, list[str]]:
    """Score a link target based on its path shape."""
    parsed = urlparse(href)
    path = (parsed.path or "/").lower()
    reasons: list[str] = []
    score = 0.0

    if any(hint in path for hint in PATH_HINTS):
        score += 1.5
        reasons.append("path_hint")
    if path in {"/links", "/friends", "/friend-links", "/friendlink", "/blogroll"}:
        score += 0.5
        reasons.append("canonical_path")
    if any(token in path for token in ("friend", "link", "blogroll")):
        score += 0.5
        reasons.append("path_keyword")
    if any(token in path for token in ("about", "archive", "tag", "rss", "feed", "contact")):
        score -= 1.0
        reasons.append("negative_path")
    return score, reasons


def _container_score(anchor: Tag) -> tuple[float, list[str]]:
    """Score an anchor based on the HTML structure around it."""
    current: Tag | None = anchor
    score = 0.0
    reasons: list[str] = []
    visited: set[str] = set()

    while current is not None:
        current = current.parent if isinstance(current.parent, Tag) else None
        if current is None:
            break
        name = current.name or ""
        if name in POSITIVE_CONTAINERS and name not in visited:
            score += 0.5
            reasons.append(f"{name}_container")
            visited.add(name)
        if name in NEGATIVE_CONTAINERS and name not in visited:
            score -= 0.5
            reasons.append(f"{name}_container")
            visited.add(name)

        classes = " ".join(current.get("class", []))
        identifier = str(current.get("id", ""))
        combined = f"{classes} {identifier}".lower()
        if combined and _text_contains_any(combined, PAGE_KEYWORDS):
            score += 1.0
            reasons.append("container_keyword")
            break
        if combined and _text_contains_any(combined, NEGATIVE_KEYWORDS):
            score -= 1.0
            reasons.append("container_negative_keyword")
            break

    return score, reasons


def collect_homepage_navigation_candidates(base_url: str, html: str) -> list[PageCandidate]:
    """Collect and score homepage anchors that could point to friend-link pages."""
    soup = BeautifulSoup(html, "html.parser")
    deduped: dict[str, PageCandidate] = {}

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        absolute_url = urljoin(base_url, href)
        anchor_text = _clean_text(anchor.get_text(" ", strip=True))
        context_text = _anchor_context(anchor)
        combined_text = _clean_text(f"{anchor_text} {context_text}")

        score = 0.0
        reasons: list[str] = []
        if _text_contains_any(anchor_text, STRONG_PAGE_KEYWORDS):
            score += 2.0
            reasons.append("anchor_strong_keyword")
        elif _text_contains_any(anchor_text, WEAK_PAGE_KEYWORDS):
            score += 0.5
            reasons.append("anchor_weak_keyword")
        if context_text and _text_contains_any(context_text, STRONG_PAGE_KEYWORDS):
            score += 1.0
            reasons.append("context_strong_keyword")
        elif context_text and _text_contains_any(context_text, WEAK_PAGE_KEYWORDS):
            score += 0.25
            reasons.append("context_weak_keyword")
        if _text_contains_any(combined_text, NEGATIVE_KEYWORDS):
            score -= 1.5
            reasons.append("negative_keyword")

        path_score, path_reasons = _path_score(href)
        score += path_score
        reasons.extend(path_reasons)

        container_score, container_reasons = _container_score(anchor)
        score += container_score
        reasons.extend(container_reasons)

        if not anchor_text and not context_text and score <= 0:
            continue

        candidate = PageCandidate(
            url=absolute_url,
            score=score,
            anchor_text=anchor_text,
            context_text=context_text,
            reasons=tuple(dict.fromkeys(reasons)),
        )
        existing = deduped.get(candidate.url)
        if existing is None or candidate.score > existing.score:
            deduped[candidate.url] = candidate

    return sorted(
        deduped.values(),
        key=lambda item: (item.score, len(item.reasons), item.url),
        reverse=True,
    )


def discover_friend_link_page_candidates(
    base_url: str,
    html: str,
    *,
    min_page_score: float = MIN_PAGE_SCORE,
) -> list[PageCandidate]:
    """Return ranked homepage candidate pages including deterministic path probes."""
    candidates = collect_homepage_navigation_candidates(base_url, html)
    if candidates and candidates[0].score >= min_page_score:
        return candidates

    existing_urls = {candidate.url for candidate in candidates}
    for hint in PATH_HINTS:
        url = urljoin(base_url, hint)
        if url in existing_urls:
            continue
        candidates.append(
            PageCandidate(
                url=url,
                score=1.0,
                anchor_text="",
                context_text="fallback path probe",
                reasons=("fallback_path_probe",),
            )
        )

    return sorted(
        candidates,
        key=lambda item: (item.score, len(item.reasons), item.url),
        reverse=True,
    )


def discover_friend_links_pages(
    base_url: str,
    html: str,
    *,
    min_page_score: float = MIN_PAGE_SCORE,
) -> list[str]:
    """Infer friend-link page URLs from scored homepage candidates."""
    candidates = discover_friend_link_page_candidates(
        base_url,
        html,
        min_page_score=min_page_score,
    )
    selected = [candidate.url for candidate in candidates if candidate.score >= min_page_score]
    if selected:
        return selected
    return [candidate.url for candidate in candidates]
