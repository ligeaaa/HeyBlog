"""Compatibility shim for crawler.filters."""

from crawler.filters import BLOCKED_TLDS
from crawler.filters import LinkDecision
from crawler.filters import decide_blog_candidate
from crawler.filters import is_blog_candidate

__all__ = [
    "BLOCKED_TLDS",
    "LinkDecision",
    "decide_blog_candidate",
    "is_blog_candidate",
]
