"""Compatibility wrapper for friend-link page discovery."""

from crawler.crawling.discovery import CONTEXT_TAGS
from crawler.crawling.discovery import NEGATIVE_KEYWORDS
from crawler.crawling.discovery import PAGE_KEYWORDS
from crawler.crawling.discovery import PATH_HINTS
from crawler.crawling.discovery import discover_friend_links_pages

__all__ = [
    "CONTEXT_TAGS",
    "NEGATIVE_KEYWORDS",
    "PAGE_KEYWORDS",
    "PATH_HINTS",
    "discover_friend_links_pages",
]
