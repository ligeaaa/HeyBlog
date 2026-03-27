"""Compatibility shims for crawler modules moved to top-level crawler package."""

from crawler.discovery import discover_friend_links_pages
from crawler.extractor import ExtractedLink
from crawler.extractor import extract_candidate_links
from crawler.fetcher import FetchResult
from crawler.fetcher import Fetcher
from crawler.filters import LinkDecision
from crawler.filters import decide_blog_candidate
from crawler.filters import is_blog_candidate
from crawler.normalizer import NormalizedUrl
from crawler.normalizer import normalize_url
from crawler.pipeline import CrawlPipeline

__all__ = [
    "CrawlPipeline",
    "ExtractedLink",
    "FetchResult",
    "Fetcher",
    "LinkDecision",
    "NormalizedUrl",
    "decide_blog_candidate",
    "discover_friend_links_pages",
    "extract_candidate_links",
    "is_blog_candidate",
    "normalize_url",
]
