"""Compatibility shim for crawler.extractor."""

from crawler.extractor import ExtractedLink
from crawler.extractor import NEGATIVE_SECTION_KEYWORDS
from crawler.extractor import SECTION_KEYWORDS
from crawler.extractor import STRUCTURAL_CONTAINERS
from crawler.extractor import extract_candidate_links

__all__ = [
    "ExtractedLink",
    "NEGATIVE_SECTION_KEYWORDS",
    "SECTION_KEYWORDS",
    "STRUCTURAL_CONTAINERS",
    "extract_candidate_links",
]
