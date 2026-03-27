"""Compatibility shim for crawler runtime service."""

from crawler.runtime import CrawlerRuntimeService
from crawler.runtime import RuntimeSnapshot
from crawler.runtime import utc_now

__all__ = ["CrawlerRuntimeService", "RuntimeSnapshot", "utc_now"]
