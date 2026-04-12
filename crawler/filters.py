"""Filter extracted links to keep only deterministic external blog homepages."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

PLATFORM_BLOCKLIST = {
    "bsky.app",
    "discord.com",
    "discord.gg",
    "facebook.com",
    "fb.com",
    "github.com",
    "instagram.com",
    "linkedin.com",
    "linkedin.cn",
    "linkedinjobs.com",
    "linktr.ee",
    "medium.com",
    "reddit.com",
    "threads.net",
    "t.co",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "xiaohongshu.com",
    "youtu.be",
    "zhihu.com",
    "weibo.com",
    "bilibili.com",
    "youtube.com",
    "youtube-nocookie.com",
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
BLOCKED_TLDS = (".gov", ".gov.cn", ".org", ".edu")
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


def _has_extra_location_parts(*, query: str, fragment: str) -> bool:
    """Return True when a URL carries query or fragment payload beyond the homepage."""
    return bool(query or fragment)


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
    # Friend-link directories usually point to the target blog homepage rather than
    # a deep article or section path, so we keep only root URLs here.
    if not _is_root_like_path(parsed.path):
        return LinkDecision(False, score, ("non_root_path",), hard_blocked=True)
    if _has_extra_location_parts(query=parsed.query, fragment=parsed.fragment):
        return LinkDecision(False, score, ("non_root_location",), hard_blocked=True)
    if any(path.endswith(suffix) for suffix in FILE_SUFFIX_BLOCKLIST):
        return LinkDecision(False, score, ("asset_suffix",), hard_blocked=True)
    if _path_has_blocked_segment(path):
        return LinkDecision(False, score, ("blocked_path",), hard_blocked=True)

    # Passing all hard rules is now sufficient for acceptance.
    return LinkDecision(True, score, ("passed_hard_filters",), hard_blocked=False)


def is_blog_candidate(url: str, source_domain: str) -> bool:
    """Return True when a link should be treated as a blog candidate."""
    return decide_blog_candidate(url, source_domain).accepted
