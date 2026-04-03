"""Central crawler logging boundary."""

from __future__ import annotations

from pathlib import Path

from persistence_api.repository import RepositoryProtocol


class CrawlerLogger:
    """Encapsulate crawler log writes so logging policy lives in one place."""

    def __init__(self, repository: RepositoryProtocol) -> None:
        self.repository = repository

    def bootstrap_success(self, seed_path: Path) -> None:
        """Record a successful seed bootstrap."""
        self.repository.add_log(stage="bootstrap", result="success", message=f"Imported seeds from {seed_path}")

    def crawl_success(self, *, blog_id: int, blog_url: str) -> None:
        """Record a successful blog crawl."""
        self.repository.add_log(blog_id=blog_id, stage="crawl", result="success", message=f"Crawled {blog_url}")

    def crawl_error(self, *, blog_id: int, error: Exception) -> None:
        """Record a failed blog crawl."""
        self.repository.add_log(blog_id=blog_id, stage="crawl", result="error", message=str(error))

