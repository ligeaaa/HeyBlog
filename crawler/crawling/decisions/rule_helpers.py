"""Shared deterministic predicates for crawler URL rule filtering."""

from __future__ import annotations

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


def path_has_blocked_segment(path: str) -> bool:
    """Return whether the path matches a known non-homepage URL pattern."""
    lowered = path.lower()
    return any(lowered == blocked or lowered.startswith(f"{blocked}/") for blocked in PATH_BLOCKLIST)


def is_root_like_path(path: str) -> bool:
    """Return whether the path still looks like a site homepage."""
    return (path or "/") == "/"


def has_extra_location_parts(*, query: str, fragment: str) -> bool:
    """Return whether the URL carries extra query or fragment state."""
    return bool(query or fragment)


def matches_blocked_domain(domain: str, blocklist: tuple[str, ...] | set[str]) -> bool:
    """Return whether a domain exactly matches or is nested under a blocked domain."""
    return any(domain == blocked or domain.endswith(f".{blocked}") for blocked in blocklist)


def matches_exact_url(normalized_url: str, exact_url_blocklist: tuple[str, ...]) -> bool:
    """Return whether the normalized candidate URL is explicitly blocked."""
    normalized_blocklist = {value.rstrip("/") for value in exact_url_blocklist}
    return normalized_url.rstrip("/") in normalized_blocklist


def matches_prefix_blocklist(normalized_url: str, prefix_blocklist: tuple[str, ...]) -> bool:
    """Return whether the normalized candidate URL starts with a blocked prefix."""
    normalized = normalized_url.rstrip("/")
    return any(normalized.startswith(prefix.rstrip("/")) for prefix in prefix_blocklist)


def has_asset_suffix(path: str) -> bool:
    """Return whether the path ends with a blocked asset-like suffix."""
    lowered = (path or "/").lower()
    return any(lowered.endswith(suffix) for suffix in FILE_SUFFIX_BLOCKLIST)
