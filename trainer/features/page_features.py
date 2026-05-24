"""Blog-specific page and context feature extraction."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup


BLOG_SIGNAL_KEYWORDS = {
    "feed": ("rss", "atom", "json feed", "订阅", "feed"),
    "archive": ("archive", "archives", "归档", "存档", "timeline", "年月"),
    "taxonomy": ("tag", "tags", "category", "categories", "标签", "分类", "专题"),
    "post": ("post", "posts", "article", "articles", "entry", "entries", "文章", "日志", "随笔"),
    "friend_links": ("friend links", "blogroll", "links", "友链", "友情链接", "邻居"),
    "comments": ("comment", "comments", "reply", "replies", "评论", "留言"),
    "about": ("about", "about me", "profile", "关于", "关于我", "自我介绍"),
    "personal": ("personal", "indieweb", "homepage", "我", "我的", "生活", "折腾", "碎碎念"),
}

NON_BLOG_SIGNAL_KEYWORDS = {
    "company": ("company", "enterprise", "business", "公司", "企业", "官网", "官方"),
    "commerce": ("pricing", "product", "products", "solution", "solutions", "cart", "shop", "定价", "产品", "方案"),
    "career": ("career", "careers", "jobs", "招聘", "加入我们"),
    "legal": ("privacy policy", "terms of service", "cookie policy", "隐私政策", "服务条款"),
}

MICROFORMAT_TOKENS = ("h-entry", "h-feed", "h-card", "p-author", "dt-published", "u-url", "rel-me", "rel-tag")
DATE_PATTERN = re.compile(r"\b(?:19|20)\d{2}(?:[-/.年](?:0?[1-9]|1[0-2]))?(?:[-/.月](?:0?[1-9]|[12]\d|3[01]))?", re.IGNORECASE)
URL_PATTERN = re.compile(r"https?://", re.IGNORECASE)
WORD_PATTERN = re.compile(r"[0-9a-z\u4e00-\u9fff]+", re.IGNORECASE)


def _safe_ratio(numerator: int, denominator: int) -> float:
    """Return a bounded ratio and avoid divide-by-zero errors.

    Args:
        numerator: Count used as the ratio numerator.
        denominator: Count used as the ratio denominator.

    Returns:
        ``numerator / denominator`` when possible, otherwise ``0.0``.
    """

    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _contains_markup(text: str) -> bool:
    """Detect whether one text field still looks like HTML.

    Args:
        text: Raw sample text or crawler context text.

    Returns:
        ``True`` when the text contains common HTML markers.
    """

    lowered = text.lower()
    return "<html" in lowered or "<body" in lowered or "<a " in lowered or "<article" in lowered


def _visible_text(raw_text: str) -> str:
    """Extract visible text from HTML-like strings while preserving plain text.

    Args:
        raw_text: Raw sample text, which may be plain text or HTML.

    Returns:
        Lower-cased visible text suitable for keyword matching.
    """

    if not raw_text:
        return ""
    if not _contains_markup(raw_text):
        return " ".join(raw_text.lower().split())
    soup = BeautifulSoup(raw_text, "html.parser")
    for element in soup(["script", "style", "noscript"]):
        element.decompose()
    return " ".join(soup.get_text(" ", strip=True).lower().split())


def _keyword_count(text: str, keywords: tuple[str, ...]) -> int:
    """Count keyword occurrences in normalized text.

    Args:
        text: Lower-cased text to scan.
        keywords: Keyword variants representing one semantic signal.

    Returns:
        Total count of keyword occurrences.
    """

    return sum(text.count(keyword.lower()) for keyword in keywords)


def _html_feature_counts(raw_text: str) -> dict[str, float]:
    """Extract DOM and semantic-markup counts when HTML is available.

    Args:
        raw_text: Raw sample text, potentially containing HTML.

    Returns:
        A small dictionary of HTML-derived numeric features.
    """

    if not _contains_markup(raw_text):
        return {
            "page:html_present": 0.0,
            "page:anchor_count": 0.0,
            "page:article_count": 0.0,
            "page:feed_link_count": 0.0,
            "page:rel_tag_count": 0.0,
            "page:microformat_count": 0.0,
        }

    soup = BeautifulSoup(raw_text, "html.parser")
    link_rels = [
        " ".join(str(token).lower() for token in link.get("rel", []))
        for link in soup.find_all("link")
    ]
    class_text = " ".join(
        " ".join(str(token).lower() for token in tag.get("class", []))
        for tag in soup.find_all(True)
    )
    return {
        "page:html_present": 1.0,
        "page:anchor_count": float(len(soup.find_all("a", href=True))),
        "page:article_count": float(len(soup.find_all("article"))),
        "page:feed_link_count": float(sum(1 for rel in link_rels if "alternate" in rel or "feed" in rel)),
        "page:rel_tag_count": float(sum(1 for rel in link_rels if "tag" in rel)),
        "page:microformat_count": float(sum(class_text.count(token) for token in MICROFORMAT_TOKENS)),
    }


def extract_page_features(raw_text: str) -> dict[str, float]:
    """Extract blog-semantic features from page text or anchor context.

    Args:
        raw_text: Plain text, HTML, or crawler anchor-context text available for
            one candidate.

    Returns:
        Feature dictionary capturing feed/archive/taxonomy/post/comment,
        personal-site, company-site, date, URL, and optional DOM signals.
    """

    text = _visible_text(raw_text)
    tokens = WORD_PATTERN.findall(text)
    token_count = len(tokens)
    features: dict[str, float] = {
        "page:text_missing": 1.0 if not text else 0.0,
        "page:text_length": float(len(text)),
        "page:token_count": float(token_count),
        "page:date_count": float(len(DATE_PATTERN.findall(text))),
        "page:url_count": float(len(URL_PATTERN.findall(text))),
    }
    features.update(_html_feature_counts(raw_text))

    blog_signal_total = 0
    for group, keywords in BLOG_SIGNAL_KEYWORDS.items():
        count = _keyword_count(text, keywords)
        blog_signal_total += count
        features[f"page:blog_signal:{group}"] = float(count)

    non_blog_signal_total = 0
    for group, keywords in NON_BLOG_SIGNAL_KEYWORDS.items():
        count = _keyword_count(text, keywords)
        non_blog_signal_total += count
        features[f"page:non_blog_signal:{group}"] = float(count)

    features["page:blog_signal_total"] = float(blog_signal_total)
    features["page:non_blog_signal_total"] = float(non_blog_signal_total)
    features["page:blog_signal_density"] = _safe_ratio(blog_signal_total, token_count)
    features["page:non_blog_signal_density"] = _safe_ratio(non_blog_signal_total, token_count)
    features["page:date_density"] = _safe_ratio(int(features["page:date_count"]), token_count)
    return features


def page_signal_tokens(raw_text: str, *, max_text_tokens: int = 96) -> list[str]:
    """Build sparse text tokens for TF-IDF models from page/context text.

    Args:
        raw_text: Plain text, HTML, or crawler anchor-context text.
        max_text_tokens: Maximum raw lexical tokens to expose per sample.

    Returns:
        Prefixed tokens representing detected blog signals plus a bounded text
        sample.
    """

    text = _visible_text(raw_text)
    if not text:
        return []

    tokens: list[str] = []
    for group, keywords in BLOG_SIGNAL_KEYWORDS.items():
        if _keyword_count(text, keywords) > 0:
            tokens.append(f"page_blog_signal:{group}")
    for group, keywords in NON_BLOG_SIGNAL_KEYWORDS.items():
        if _keyword_count(text, keywords) > 0:
            tokens.append(f"page_non_blog_signal:{group}")
    if DATE_PATTERN.search(text):
        tokens.append("page_has_date")
    if URL_PATTERN.search(text):
        tokens.append("page_has_url")
    tokens.extend(f"page_text:{token.lower()}" for token in WORD_PATTERN.findall(text)[:max_text_tokens])
    return tokens
