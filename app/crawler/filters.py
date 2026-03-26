"""Filter extracted links to keep only likely external blogs."""

from __future__ import annotations

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
    "/login",
    "/register",
    "/contact",
}


def is_blog_candidate(url: str, source_domain: str) -> bool:
    """Return True when a link should be treated as a blog candidate."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if not parsed.scheme.startswith("http"):
        return False
    if not domain or domain == source_domain:
        return False
    if any(domain == blocked or domain.endswith(f".{blocked}") for blocked in PLATFORM_BLOCKLIST):
        return False
    if parsed.path.lower() in PATH_BLOCKLIST:
        return False
    return True
