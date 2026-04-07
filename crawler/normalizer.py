"""Compatibility wrapper for URL normalization."""

from crawler.crawling.normalization import NormalizedUrl
from crawler.crawling.normalization import TRACKING_PARAMS
from crawler.crawling.normalization import BlogIdentityResolution
from crawler.crawling.normalization import IDENTITY_RULESET_VERSION
from crawler.crawling.normalization import normalize_url
from crawler.crawling.normalization import resolve_blog_identity

__all__ = [
    "BlogIdentityResolution",
    "IDENTITY_RULESET_VERSION",
    "NormalizedUrl",
    "TRACKING_PARAMS",
    "normalize_url",
    "resolve_blog_identity",
]
