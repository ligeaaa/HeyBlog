"""Compatibility shim for crawler.utils."""

from crawler.utils import clean_text
from crawler.utils import text_contains_any
from crawler.utils import unique_in_order

__all__ = ["clean_text", "text_contains_any", "unique_in_order"]
