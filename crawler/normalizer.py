"""Compatibility wrapper for URL normalization."""

from crawler.crawling.normalization import NormalizedUrl
from crawler.crawling.normalization import TRACKING_PARAMS
from crawler.crawling.normalization import normalize_url

__all__ = ["NormalizedUrl", "TRACKING_PARAMS", "normalize_url"]
