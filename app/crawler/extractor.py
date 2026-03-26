"""Extract candidate hyperlinks from crawled HTML pages."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup


@dataclass(slots=True)
class ExtractedLink:
    """Represent one extracted anchor link."""

    url: str
    text: str


def extract_candidate_links(base_url: str, html: str) -> list[ExtractedLink]:
    """Parse HTML and return normalized absolute links."""
    soup = BeautifulSoup(html, "html.parser")
    links: list[ExtractedLink] = []
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"].strip())
        text = anchor.get_text(" ", strip=True)
        links.append(ExtractedLink(url=url, text=text))
    return links
