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
    """Describe the deterministic outcome of evaluating one extracted link.

    Attributes:
        accepted: Whether the candidate passed the crawler's hard filtering
            rules and should continue as a blog candidate.
        score: Legacy scoring field preserved for compatibility with older
            decision interfaces. The current rules use hard accept/reject logic,
            so this value remains ``0.0``.
        reasons: Machine-readable reason codes explaining why the link was
            accepted or rejected.
        hard_blocked: Whether the link was rejected by a non-recoverable hard
            rule rather than a softer heuristic.
    """

    accepted: bool
    score: float
    reasons: tuple[str, ...]
    hard_blocked: bool = False


def _path_has_blocked_segment(path: str) -> bool:
    """Return whether the path matches a known non-homepage URL pattern.

    Args:
        path: URL path component to inspect.

    Returns:
        ``True`` when the path equals or is nested under one of the blocked
        crawler path prefixes such as ``/feed`` or ``/login``.
    """
    lowered = path.lower()
    return any(lowered == blocked or lowered.startswith(f"{blocked}/") for blocked in PATH_BLOCKLIST)


def _is_root_like_path(path: str) -> bool:
    """Return whether the path still looks like a site homepage.

    Args:
        path: URL path component to inspect.

    Returns:
        ``True`` only when the path is empty or exactly ``/``.
    """
    return (path or "/") == "/"


def _has_extra_location_parts(*, query: str, fragment: str) -> bool:
    """Return whether the URL carries extra query or fragment state.

    Args:
        query: Parsed query-string portion of the URL.
        fragment: Parsed fragment identifier portion of the URL.

    Returns:
        ``True`` when either a query string or fragment is present, which makes
        the URL less likely to represent a clean homepage.
    """
    return bool(query or fragment)


def _matches_blocked_domain(domain: str, blocklist: tuple[str, ...] | set[str]) -> bool:
    """Return whether a domain matches one of the blocked domains.

    Args:
        domain: Lower-cased candidate domain being evaluated.
        blocklist: Exact domains whose own hostnames and subdomains should be
            rejected.

    Returns:
        ``True`` when the candidate domain is exactly blocked or is a subdomain
        of a blocked domain.
    """
    return any(domain == blocked or domain.endswith(f".{blocked}") for blocked in blocklist)


def _matches_exact_url(normalized_url: str, exact_url_blocklist: tuple[str, ...]) -> bool:
    """Return whether the normalized candidate URL is explicitly blocked.

    Args:
        normalized_url: Candidate URL normalized for exact comparison.
        exact_url_blocklist: Absolute URLs that should be rejected as-is.

    Returns:
        ``True`` when the candidate exactly matches one of the blocked URLs
        after trailing-slash normalization.
    """
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
    """Classify whether an extracted link should be treated as a blog homepage.

    Args:
        url: Absolute extracted URL being evaluated.
        source_domain: Domain of the page where the link was discovered.
        link_text: Visible anchor text associated with the link. Kept for API
            compatibility even though the current rules do not use it.
        context_text: Nearby container text associated with the link. Kept for
            compatibility with richer decision strategies.
        domain_blocklist: Additional blocked domains supplied by crawler
            configuration.
        blocked_tlds: TLD suffixes that should always be rejected.
        exact_url_blocklist: Explicit absolute URLs that should be rejected.
        prefix_blocklist: URL prefixes that should be rejected before any other
            acceptance logic runs.

    Returns:
        A ``LinkDecision`` describing whether the link survives the crawler's
        hard homepage filters and, if not, which rule rejected it.
    """
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
    """Return whether an extracted URL passes the default blog candidate rules.

    Args:
        url: Absolute extracted URL being evaluated.
        source_domain: Domain of the source page that contained the link.

    Returns:
        ``True`` when ``decide_blog_candidate`` accepts the URL.
    """
    return decide_blog_candidate(url, source_domain).accepted
