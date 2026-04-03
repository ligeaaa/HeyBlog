"""Crawler-specific exception hierarchy."""

from __future__ import annotations


class CrawlerError(Exception):
    """Base class for crawler-specific failures."""


class CrawlerRuntimeError(CrawlerError):
    """Raised when runtime actions cannot be completed safely."""

