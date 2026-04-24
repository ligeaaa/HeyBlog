"""Central crawler logging boundary."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class CrawlerLogger:
    """Encapsulate crawler log writes behind one small boundary.

    This keeps the crawler pipeline focused on behavior while centralizing log
    message wording and structured metadata in one place.
    """

    def _emit(
        self,
        *,
        level: int,
        message: str,
        stage: str,
        extra: dict[str, object],
    ) -> None:
        """Emit one crawler log entry with a normalized stage payload.

        Args:
            level: Logging level used for the emitted entry.
            message: Human-readable log message.
            stage: Crawler stage marker stored in the structured payload.
            extra: Additional structured fields to merge into the log record.

        Returns:
            ``None``. The log entry is emitted to the module logger.
        """

        logger.log(level, message, extra={"stage": stage, **extra})

    def bootstrap_success(self, seed_path: Path) -> None:
        """Log that the seed bootstrap flow completed successfully.

        Args:
            seed_path: CSV seed file that was imported.

        Returns:
            ``None``. A structured log entry is emitted.
        """
        self._emit(
            level=logging.INFO,
            message="bootstrap succeeded",
            stage="bootstrap",
            extra={"seed_path": str(seed_path)},
        )

    def crawl_success(self, *, blog_id: int, blog_url: str) -> None:
        """Log that one blog crawl completed successfully.

        Args:
            blog_id: Identifier of the crawled blog.
            blog_url: URL of the crawled blog.

        Returns:
            ``None``. A structured log entry is emitted.
        """
        self._emit(
            level=logging.INFO,
            message="crawl succeeded",
            stage="crawl",
            extra={"blog_id": blog_id, "blog_url": blog_url},
        )

    def crawl_error(self, *, blog_id: int, error: Exception) -> None:
        """Log that one blog crawl failed.

        Args:
            blog_id: Identifier of the blog whose crawl failed.
            error: Exception raised while processing the blog.

        Returns:
            ``None``. A structured warning log entry is emitted.
        """
        self._emit(
            level=logging.WARNING,
            message="crawl failed",
            stage="crawl",
            extra={"blog_id": blog_id, "error": str(error)},
        )
