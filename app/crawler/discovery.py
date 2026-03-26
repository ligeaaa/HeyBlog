from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup


KEYWORDS = ("友链", "友情链接", "links", "blogroll", "friends", "邻居", "小伙伴")
PATH_HINTS = ("/links", "/friends", "/friend-links", "/blogroll")


def discover_friend_links_pages(base_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        text = anchor.get_text(" ", strip=True).lower()
        absolute_url = urljoin(base_url, href)
        lower_href = href.lower()
        if any(keyword.lower() in text for keyword in KEYWORDS) or any(
            hint in lower_href for hint in PATH_HINTS
        ):
            candidates.append(absolute_url)

    if not candidates:
        candidates.extend(urljoin(base_url, hint) for hint in PATH_HINTS)

    deduped: list[str] = []
    seen = set()
    for candidate in candidates:
        if candidate not in seen:
            deduped.append(candidate)
            seen.add(candidate)
    return deduped
