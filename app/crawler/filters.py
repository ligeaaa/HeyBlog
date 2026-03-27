"""Filter extracted links to keep only likely external blogs."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


PLATFORM_BLOCKLIST = {
    "github.com",
    "twitter.com",
    "x.com",
    "zhihu.com",
    "weibo.com",
    "bilibili.com",
    "youtube.com",
    "t.me",
    "telegram.me",
}
PATH_BLOCKLIST = {
    "/admin",
    "/api",
    "/archive",
    "/archives",
    "/contact",
    "/feed",
    "/login",
    "/register",
    "/rss",
    "/search",
}
NEGATIVE_CONTEXT_KEYWORDS = (
    "contact",
    "donate",
    "donation",
    "github",
    "rss",
    "search",
    "sitemap",
    "sponsor",
    "sponsored",
    "telegram",
    "twitter",
)
POSITIVE_CONTEXT_KEYWORDS = (
    "blog",
    "friend",
    "homepage",
    "site",
    "友链",
    "友情链接",
    "伙伴",
    "邻居",
)
BLOCKED_TLDS = (".gov", ".edu")
FILE_SUFFIX_BLOCKLIST = (
    ".7z",
    ".css",
    ".csv",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".pdf",
    ".png",
    ".svg",
    ".tar",
    ".xml",
    ".zip",
)


@dataclass(slots=True)
class LinkDecision:
    """Represent one deterministic filtering decision."""

    accepted: bool
    score: float
    reasons: tuple[str, ...]
    hard_blocked: bool = False


def _path_has_blocked_segment(path: str) -> bool:
    """Return True when the path is clearly not a blog homepage."""
    lowered = path.lower()
    return any(lowered == blocked or lowered.startswith(f"{blocked}/") for blocked in PATH_BLOCKLIST)


def _text_contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    """Case-insensitive keyword helper."""
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def decide_blog_candidate(
    url: str,
    source_domain: str,
    *,
    link_text: str = "",
    context_text: str = "",
    domain_blocklist: tuple[str, ...] = (),
    blocked_tlds: tuple[str, ...] = BLOCKED_TLDS,
    exact_url_blocklist: tuple[str, ...] = (),
    prefix_blocklist: tuple[str, ...] = (),
) -> LinkDecision:
    """Score and classify whether a link should be treated as a blog candidate."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    normalized_url = url.rstrip("/")
    path = parsed.path.lower() or "/"
    reasons: list[str] = []
    score = 0.0

    if not parsed.scheme.startswith("http"):
        return LinkDecision(False, score, ("non_http_scheme",), hard_blocked=True)
    if not domain or domain == source_domain:
        return LinkDecision(False, score, ("same_domain",), hard_blocked=True)
    if normalized_url in exact_url_blocklist:
        return LinkDecision(False, score, ("exact_url_blocked",), hard_blocked=True)
    if any(normalized_url.startswith(prefix) for prefix in prefix_blocklist):
        return LinkDecision(False, score, ("prefix_blocked",), hard_blocked=True)
    if any(domain == blocked or domain.endswith(f".{blocked}") for blocked in PLATFORM_BLOCKLIST):
        return LinkDecision(False, score, ("platform_blocked",), hard_blocked=True)
    if any(domain == blocked or domain.endswith(f".{blocked}") for blocked in domain_blocklist):
        return LinkDecision(False, score, ("domain_blocked",), hard_blocked=True)
    if any(domain.endswith(tld) for tld in blocked_tlds):
        return LinkDecision(False, score, ("blocked_tld",), hard_blocked=True)
    if any(path.endswith(suffix) for suffix in FILE_SUFFIX_BLOCKLIST):
        return LinkDecision(False, score, ("asset_suffix",), hard_blocked=True)
    if _path_has_blocked_segment(path):
        return LinkDecision(False, score, ("blocked_path",), hard_blocked=True)

    combined_text = f"{link_text} {context_text}".strip()
    if _text_contains_any(combined_text, NEGATIVE_CONTEXT_KEYWORDS):
        reasons.append("negative_context")
        score -= 1.0
    if _text_contains_any(combined_text, POSITIVE_CONTEXT_KEYWORDS):
        reasons.append("positive_context")
        score += 1.0
    if path in {"", "/"}:
        reasons.append("root_path")
        score += 0.5
    if "." in domain and len(domain.split(".")) >= 2:
        reasons.append("external_domain")
        score += 0.5

    accepted = score >= 0.5
    if not accepted and not reasons:
        reasons.append("insufficient_signal")
    return LinkDecision(accepted, score, tuple(reasons), hard_blocked=False)


def is_blog_candidate(url: str, source_domain: str) -> bool:
    """Return True when a link should be treated as a blog candidate."""
    return decide_blog_candidate(url, source_domain).accepted
