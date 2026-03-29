"""Filter extracted links to keep only likely external blogs."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from crawler.utils import text_contains_any


PLATFORM_BLOCKLIST = {
    "facebook.com",
    "github.com",
    "instagram.com",
    "linkedin.com",
    "linkedin.cn",
    "linkedinjobs.com",
    "linktr.ee",
    "medium.com",
    "reddit.com",
    "threads.net",
    "tiktok.com",
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
BLOCKED_TLDS = (".gov", ".org", ".edu")
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


@dataclass
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


def _is_root_like_path(path: str) -> bool:
    """Return True only for homepage-like paths."""
    return (path or "/") == "/"


def _matches_blocked_domain(domain: str, blocklist: tuple[str, ...] | set[str]) -> bool:
    """Return True when the domain matches or is nested under a blocked domain."""
    return any(domain == blocked or domain.endswith(f".{blocked}") for blocked in blocklist)


def _matches_exact_url(normalized_url: str, exact_url_blocklist: tuple[str, ...]) -> bool:
    """Return True when the candidate URL matches a blocked absolute URL."""
    normalized_blocklist = {value.rstrip("/") for value in exact_url_blocklist}
    return normalized_url in normalized_blocklist


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
    normalized_source_domain = source_domain.lower()
    normalized_url = url.rstrip("/")
    path = parsed.path.lower() or "/"
    reasons: list[str] = []
    score = 0.0

    # Apply hard blocks first so clearly invalid candidates never reach the softer scoring layer.
    if not parsed.scheme.startswith("http"):
        return LinkDecision(False, score, ("non_http_scheme",), hard_blocked=True)
    if not domain or domain == normalized_source_domain:
        return LinkDecision(False, score, ("same_domain",), hard_blocked=True)
    if _matches_exact_url(normalized_url, exact_url_blocklist):
        return LinkDecision(False, score, ("exact_url_blocked",), hard_blocked=True)
    if any(normalized_url.startswith(prefix) for prefix in prefix_blocklist):
        return LinkDecision(False, score, ("prefix_blocked",), hard_blocked=True)
    if _matches_blocked_domain(domain, PLATFORM_BLOCKLIST):
        return LinkDecision(False, score, ("platform_blocked",), hard_blocked=True)
    if _matches_blocked_domain(domain, domain_blocklist):
        return LinkDecision(False, score, ("domain_blocked",), hard_blocked=True)
    if any(domain.endswith(tld) for tld in blocked_tlds):
        return LinkDecision(False, score, ("blocked_tld",), hard_blocked=True)
    if not _is_root_like_path(parsed.path):
        return LinkDecision(False, score, ("non_root_path",), hard_blocked=True)
    if any(path.endswith(suffix) for suffix in FILE_SUFFIX_BLOCKLIST):
        return LinkDecision(False, score, ("asset_suffix",), hard_blocked=True)
    if _path_has_blocked_segment(path):
        return LinkDecision(False, score, ("blocked_path",), hard_blocked=True)

    # Once hard blocks pass, light context scoring can keep likely blog homepages without mixing in discovery logic.
    combined_text = f"{link_text} {context_text}".strip()
    if text_contains_any(combined_text, NEGATIVE_CONTEXT_KEYWORDS):
        reasons.append("negative_context")
        score -= 1.0
    if text_contains_any(combined_text, POSITIVE_CONTEXT_KEYWORDS):
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
