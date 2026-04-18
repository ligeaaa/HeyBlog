"""Seed bootstrap flow for the crawler."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from crawler.crawling.normalization import normalize_url
from crawler.observability.logger import CrawlerLogger
from persistence_api.repository import RepositoryProtocol


class BootstrapService:
    """Import crawler seed URLs into persistence storage.

    The bootstrap flow reads the configured seed CSV, normalizes each URL, and
    upserts the result into the blog repository so later crawl runs have an
    initial queue to process.
    """

    def __init__(self, repository: RepositoryProtocol, logger: CrawlerLogger) -> None:
        """Store the persistence and logging dependencies used by bootstrap.

        Args:
            repository: Repository interface used to create or update seed blog
                records.
            logger: Logger facade used to emit bootstrap lifecycle events.

        Returns:
            ``None``. The service stores the provided dependencies for later
            bootstrap operations.
        """
        self.repository = repository
        self.logger = logger

    def bootstrap_seeds(self, seed_path: Path) -> dict[str, Any]:
        """Import seed URLs from a CSV file into the blogs table.

        Args:
            seed_path: Filesystem path to the CSV file containing a ``url``
                column of initial crawl targets.

        Returns:
            A small result payload containing the imported seed file path and
            the number of newly created blog rows.
        """
        created = 0
        with seed_path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                raw_url = (row.get("url") or "").strip()
                if not raw_url:
                    continue
                normalized = normalize_url(raw_url)
                _, inserted = self.repository.upsert_blog(
                    url=raw_url,
                    normalized_url=normalized.normalized_url,
                    domain=normalized.domain,
                )
                created += int(inserted)
        self.logger.bootstrap_success(seed_path)
        return {"seed_path": str(seed_path), "imported": created}
