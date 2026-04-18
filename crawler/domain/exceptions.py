"""Crawler-specific exception hierarchy."""

from __future__ import annotations


class CrawlerError(Exception):
    """Base class for crawler-specific failures.

    All crawler-defined exceptions inherit from this type so callers can catch
    domain-specific failures without accidentally swallowing unrelated errors.
    """


class CrawlerRuntimeError(CrawlerError):
    """Raised when a runtime control action cannot be completed safely.

    This exception is intended for start/stop/runtime orchestration failures
    rather than per-blog crawl errors.
    """
