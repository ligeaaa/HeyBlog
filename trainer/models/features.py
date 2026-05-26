"""Feature builders used by legacy URL-decision model artifacts."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

from bs4 import BeautifulSoup

DEFAULT_TITLE_TOKEN_CHUNK_SIZE = 2
URL_KEYWORDS = (
    "blog",
    "posts",
    "post",
    "article",
    "articles",
    "archive",
    "archives",
    "tag",
    "tags",
    "category",
    "categories",
    "feed",
    "about",
    "company",
    "official",
)
TITLE_KEYWORDS = (
    "blog",
    "blogs",
    "notes",
    "note",
    "journal",
    "diary",
    "company",
    "official",
    "studio",
)
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
TOKEN_SPLIT_PATTERN = re.compile(r"[^0-9a-z\u4e00-\u9fff]+", re.IGNORECASE)
TITLE_TOKEN_PATTERN = re.compile(r"[0-9A-Za-z\u4e00-\u9fff]+")
TITLE_ALLOWED_CHAR_PATTERN = re.compile(r"[0-9A-Za-z\u4e00-\u9fff]")
DATE_PATTERN = re.compile(r"\b(?:19|20)\d{2}(?:[-/.年](?:0?[1-9]|1[0-2]))?(?:[-/.月](?:0?[1-9]|[12]\d|3[01]))?", re.IGNORECASE)
URL_PATTERN = re.compile(r"https?://", re.IGNORECASE)
WORD_PATTERN = re.compile(r"[0-9a-z\u4e00-\u9fff]+", re.IGNORECASE)


def _safe_ratio(numerator: int, denominator: int) -> float:
    """Return ``numerator / denominator`` while avoiding division by zero."""
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def tokenize_url(normalized_url: str) -> list[str]:
    """Tokenize one normalized URL for legacy TF-IDF model input."""
    parsed = urlparse(normalized_url)
    source = " ".join([parsed.netloc, parsed.path.replace("/", " "), parsed.query.replace("&", " ")]).lower()
    return [token for token in TOKEN_SPLIT_PATTERN.split(source) if token]


def extract_url_features(normalized_url: str) -> dict[str, float]:
    """Extract structured URL features expected by legacy pickled models."""
    parsed = urlparse(normalized_url)
    host_labels = [label for label in parsed.netloc.split(".") if label]
    path_segments = [segment for segment in parsed.path.split("/") if segment]
    path_text = " ".join(path_segments).lower()
    digit_count = sum(1 for char in normalized_url if char.isdigit())
    features = {
        "url:path_depth": float(len(path_segments)),
        "url:path_length": float(len(parsed.path)),
        "url:is_root_path": 1.0 if parsed.path in {"", "/"} else 0.0,
        "url:has_query": 1.0 if bool(parsed.query) else 0.0,
        "url:subdomain_count": float(max(0, len(host_labels) - 2)),
        "url:url_length": float(len(normalized_url)),
        "url:domain_length": float(len(parsed.netloc)),
        "url:hyphen_count": float(normalized_url.count("-")),
        "url:underscore_count": float(normalized_url.count("_")),
        "url:digit_ratio": _safe_ratio(digit_count, len(normalized_url)),
    }
    for keyword in URL_KEYWORDS:
        features[f"url:kw:{keyword}"] = 1.0 if keyword in path_text or keyword in parsed.netloc.lower() else 0.0
    return features


def url_char_ngrams(normalized_url: str, min_n: int, max_n: int) -> list[str]:
    """Build URL character n-grams for legacy TF-IDF model input."""
    text = normalized_url.lower().strip()
    if not text:
        return []
    tokens: list[str] = []
    for width in range(min_n, max_n + 1):
        if len(text) < width:
            continue
        for index in range(0, len(text) - width + 1):
            tokens.append(text[index : index + width])
    return tokens or [text]


def clean_title(title: str) -> str:
    """Normalize title casing and whitespace for feature extraction."""
    normalized = unicodedata.normalize("NFKC", title or "").strip().lower()
    return " ".join(normalized.split())


def tokenize_title(title: str) -> list[str]:
    """Split a title into legacy word-like runs."""
    return TITLE_TOKEN_PATTERN.findall(clean_title(title))


def tokenize_title_char_chunks(title: str, chunk_size: int = DEFAULT_TITLE_TOKEN_CHUNK_SIZE) -> list[str]:
    """Build fixed-width title chunks after dropping punctuation."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    filtered = "".join(TITLE_ALLOWED_CHAR_PATTERN.findall(clean_title(title)))
    if not filtered:
        return []
    return [filtered[index : index + chunk_size] for index in range(0, len(filtered), chunk_size)]


def title_word_ngrams(tokens: list[str], min_n: int, max_n: int) -> list[str]:
    """Create ordered word n-grams from title tokens."""
    if not tokens:
        return []
    grams: list[str] = []
    for width in range(min_n, max_n + 1):
        if len(tokens) < width:
            continue
        for index in range(0, len(tokens) - width + 1):
            grams.append(" ".join(tokens[index : index + width]))
    return grams or list(tokens)


def extract_title_features(title: str) -> dict[str, float]:
    """Extract handcrafted title statistics and keyword flags."""
    cleaned = clean_title(title)
    tokens = tokenize_title(cleaned)
    features = {
        "title:missing": 1.0 if not cleaned else 0.0,
        "title:length": float(len(cleaned)),
        "title:token_count": float(len(tokens)),
        "title:avg_token_length": (sum(len(token) for token in tokens) / len(tokens)) if tokens else 0.0,
    }
    for keyword in TITLE_KEYWORDS:
        features[f"title:kw:{keyword}"] = 1.0 if keyword in cleaned else 0.0
    return features


def _contains_markup(text: str) -> bool:
    """Return whether text looks like HTML."""
    lowered = text.lower()
    return "<html" in lowered or "<body" in lowered or "<a " in lowered or "<article" in lowered


def _visible_text(raw_text: str) -> str:
    """Extract visible lower-cased text from HTML or plain text."""
    if not raw_text:
        return ""
    if not _contains_markup(raw_text):
        return " ".join(raw_text.lower().split())
    soup = BeautifulSoup(raw_text, "html.parser")
    for element in soup(["script", "style", "noscript"]):
        element.decompose()
    return " ".join(soup.get_text(" ", strip=True).lower().split())


def _keyword_count(text: str, keywords: tuple[str, ...]) -> int:
    """Count keyword occurrences in normalized text."""
    return sum(text.count(keyword.lower()) for keyword in keywords)


def _html_feature_counts(raw_text: str) -> dict[str, float]:
    """Extract DOM and semantic-markup counts when HTML is available."""
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
    link_rels = [" ".join(str(token).lower() for token in link.get("rel", [])) for link in soup.find_all("link")]
    class_text = " ".join(" ".join(str(token).lower() for token in tag.get("class", [])) for tag in soup.find_all(True))
    return {
        "page:html_present": 1.0,
        "page:anchor_count": float(len(soup.find_all("a", href=True))),
        "page:article_count": float(len(soup.find_all("article"))),
        "page:feed_link_count": float(sum(1 for rel in link_rels if "alternate" in rel or "feed" in rel)),
        "page:rel_tag_count": float(sum(1 for rel in link_rels if "tag" in rel)),
        "page:microformat_count": float(sum(class_text.count(token) for token in MICROFORMAT_TOKENS)),
    }


def extract_page_features(raw_text: str) -> dict[str, float]:
    """Extract blog-semantic features from page text or anchor context."""
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
    """Build sparse text tokens for TF-IDF models from page/context text."""
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


def build_structured_feature_rows(samples: list[object]) -> list[dict[str, float]]:
    """Build one structured feature dictionary per runtime sample."""
    rows: list[dict[str, float]] = []
    for sample in samples:
        rows.append(
            {
                **extract_url_features(str(sample.normalized_url)),
                **extract_title_features(str(sample.title)),
                **extract_page_features(str(getattr(sample, "text", ""))),
            }
        )
    return rows


def build_tfidf_documents(
    samples: list[object],
    *,
    url_char_ngram_range: tuple[int, int],
    title_word_ngram_range: tuple[int, int],
    title_token_chunk_size: int,
) -> tuple[list[list[str]], list[list[str]]]:
    """Build URL and title/context token documents for legacy TF-IDF models."""
    url_documents = [
        url_char_ngrams(str(sample.normalized_url), *url_char_ngram_range) + tokenize_url(str(sample.normalized_url))
        for sample in samples
    ]
    title_documents: list[list[str]] = []
    for sample in samples:
        title_tokens = tokenize_title_char_chunks(str(sample.title), title_token_chunk_size)
        title_documents.append(
            title_word_ngrams(title_tokens, *title_word_ngram_range)
            + page_signal_tokens(str(getattr(sample, "text", "")))
        )
    return url_documents, title_documents

