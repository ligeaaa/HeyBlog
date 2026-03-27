"""Compatibility shim for search service entrypoint."""

from search.main import SearchService
from search.main import app
from search.main import build_search_service
from search.main import create_app

__all__ = ["SearchService", "app", "build_search_service", "create_app"]
