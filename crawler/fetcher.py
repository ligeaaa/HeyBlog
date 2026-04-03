"""Compatibility wrapper for crawler fetching."""

from crawler.crawling.fetching import httpx_fetcher as _httpx_fetcher
from crawler.crawling.fetching.base import FetchAttempt
from crawler.crawling.fetching.base import FetchResult
from crawler.crawling.fetching.httpx_fetcher import Fetcher

httpx = _httpx_fetcher.httpx

__all__ = ["FetchAttempt", "FetchResult", "Fetcher", "httpx"]
