"""Extract title and favicon-style metadata from one crawled homepage."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from bs4 import Tag

from crawler.utils import clean_text


@dataclass(slots=True)
class SiteMetadata:
    """Represent display metadata derived from one site homepage."""

    title: str | None
    icon_url: str | None


def _link_rel_tokens(link: Tag) -> set[str]:
    rel_value = link.get("rel")
    if isinstance(rel_value, str):
        return {token.strip().lower() for token in rel_value.split() if token.strip()}
    if isinstance(rel_value, list):
        return {str(token).strip().lower() for token in rel_value if str(token).strip()}
    return set()


def _icon_priority(rel_tokens: set[str]) -> int | None:
    if rel_tokens == {"shortcut", "icon"}:
        return 0
    if "icon" in rel_tokens and "apple-touch-icon" not in rel_tokens and "mask-icon" not in rel_tokens:
        return 1
    if "apple-touch-icon" in rel_tokens:
        return 2
    if "apple-touch-icon-precomposed" in rel_tokens:
        return 3
    return None


def _is_http_url(candidate_url: str) -> bool:
    parsed = urlsplit(candidate_url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _pick_icon_url(page_url: str, soup: BeautifulSoup) -> str | None:
    ranked_candidates: list[tuple[int, int, str]] = []
    for index, link in enumerate(soup.find_all("link", href=True)):
        rel_tokens = _link_rel_tokens(link)
        priority = _icon_priority(rel_tokens)
        href = str(link.get("href", "")).strip()
        if priority is None or not href:
            continue
        resolved_href = urljoin(page_url, href)
        if not _is_http_url(resolved_href):
            continue
        ranked_candidates.append((priority, index, resolved_href))

    if ranked_candidates:
        ranked_candidates.sort(key=lambda item: (item[0], item[1]))
        return ranked_candidates[0][2]

    if not _is_http_url(page_url):
        return None
    parsed = urlsplit(page_url)
    return f"{parsed.scheme}://{parsed.netloc}/favicon.ico"


def extract_site_metadata(page_url: str, html: str) -> SiteMetadata:
    """Return title and browser-tab icon metadata for one homepage HTML document."""
    soup = BeautifulSoup(html, "html.parser")
    title = None
    if soup.title is not None:
        title = clean_text(soup.title.get_text(" ", strip=True)) or None

    return SiteMetadata(title=title, icon_url=_pick_icon_url(page_url, soup))

