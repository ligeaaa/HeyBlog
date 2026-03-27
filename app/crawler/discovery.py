"""Discover likely friend-link pages from a blog homepage."""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup


KEYWORDS = ("友链", "友情链接", "links", "blogroll", "friends", "邻居", "小伙伴")
PATH_HINTS = ("/links", "/friends", "/friend-links", "/blogroll")


def discover_friend_links_pages(base_url: str, html: str) -> list[str]:
    """Infer friend-link page URLs from anchors and fallback path hints."""
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
    seen: set[str] = set()
    for candidate in candidates:
        if candidate not in seen:
            deduped.append(candidate)
            seen.add(candidate)
    return deduped

"""
1. 现在的逻辑是直接找a标签，然后判断是否在KEYWORDS和PATH_HINTS中。这样子有许多问题：例如可能找不到一些友链界面，或者错误的将其它链接判断为友链接。
2. 因此需要：
    a. 更准确的找友链界面方法
    b. 在友链界面中更准确的找友链方法
    c. 对找到的友链进行判断是否是友链，或者添加一定的过滤原则，例如屏蔽掉特定链接，或者.gov等后缀
3. 研究怎么引入大语言模型，直接MCP，我觉得这是现阶段最方便最鲁棒的做法
"""