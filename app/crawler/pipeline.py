"""Compatibility shim for crawler.pipeline."""

from crawler.pipeline import BlogErrorHook
from crawler.pipeline import BlogFinishHook
from crawler.pipeline import BlogStartHook
from crawler.pipeline import CrawlPipeline
from crawler.pipeline import ShouldStopHook

__all__ = [
    "BlogErrorHook",
    "BlogFinishHook",
    "BlogStartHook",
    "CrawlPipeline",
    "ShouldStopHook",
]
