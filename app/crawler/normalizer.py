"""Compatibility shim for crawler.normalizer."""

from crawler.normalizer import NormalizedUrl
from crawler.normalizer import TRACKING_PARAMS
from crawler.normalizer import normalize_url

__all__ = ["NormalizedUrl", "TRACKING_PARAMS", "normalize_url"]
