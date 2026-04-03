"""Compatibility wrapper for the crawler pipeline facade."""

from crawler.crawling.pipeline import BlogErrorHook
from crawler.crawling.pipeline import BlogFinishHook
from crawler.crawling.pipeline import BlogStartHook
from crawler.crawling.pipeline import CrawlPipeline
from crawler.crawling.pipeline import ShouldStopHook
from crawler.contracts.results import BlogCrawlResult
from crawler.contracts.results import CrawlRunStats
from crawler.domain.blog_node import BlogNode as BlogRecord

__all__ = [
    "BlogCrawlResult",
    "BlogErrorHook",
    "BlogFinishHook",
    "BlogRecord",
    "BlogStartHook",
    "CrawlPipeline",
    "CrawlRunStats",
    "ShouldStopHook",
]
