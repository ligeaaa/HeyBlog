"""Compatibility shim for crawler.discovery."""

from crawler.discovery import CONTEXT_TAGS
from crawler.discovery import NEGATIVE_KEYWORDS
from crawler.discovery import PAGE_KEYWORDS
from crawler.discovery import PATH_HINTS
from crawler.discovery import discover_friend_links_pages

__all__ = [
    "CONTEXT_TAGS",
    "NEGATIVE_KEYWORDS",
    "PAGE_KEYWORDS",
    "PATH_HINTS",
    "discover_friend_links_pages",
]
