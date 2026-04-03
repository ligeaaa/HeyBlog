"""Compatibility wrapper for candidate link extraction."""

from crawler.crawling.extraction import ExtractedLink
from crawler.crawling.extraction import NEGATIVE_SECTION_KEYWORDS
from crawler.crawling.extraction import SECTION_KEYWORDS
from crawler.crawling.extraction import STRUCTURAL_CONTAINERS
from crawler.crawling.extraction import extract_candidate_links

__all__ = [
    "ExtractedLink",
    "NEGATIVE_SECTION_KEYWORDS",
    "SECTION_KEYWORDS",
    "STRUCTURAL_CONTAINERS",
    "extract_candidate_links",
]
