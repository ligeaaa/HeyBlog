"""Central crawler logging boundary."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class CrawlerLogger:
    """Encapsulate crawler log writes so logging policy lives in one place."""

    def bootstrap_success(self, seed_path: Path) -> None:
        """Emit a bootstrap success event to the process logger."""
        logger.info("bootstrap succeeded", extra={"seed_path": str(seed_path), "stage": "bootstrap"})

    def crawl_success(self, *, blog_id: int, blog_url: str) -> None:
        """Emit a crawl success event to the process logger."""
        logger.info(
            "crawl succeeded",
            extra={"blog_id": blog_id, "blog_url": blog_url, "stage": "crawl"},
        )

    def crawl_error(self, *, blog_id: int, error: Exception) -> None:
        """Emit a crawl failure event to the process logger."""
        logger.warning(
            "crawl failed",
            extra={"blog_id": blog_id, "error": str(error), "stage": "crawl"},
        )
