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

    The bootstrap flow first replays any durable seeds already stored in
    persistence. When no durable seeds exist yet, it reads the configured seed
    CSV, normalizes each URL, stores it in the seed table, and upserts the blog
    queue row.
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
        """Import seed URLs into the blogs table.

        Args:
            seed_path: Filesystem path to the fallback CSV file containing a
                ``url`` column of initial crawl targets. The CSV is only read
                when the durable seed table is empty.

        Returns:
            A small result payload containing the imported seed file path and
            the number of newly created blog rows.
        """
        existing_seeds = self.repository.list_seeds()
        if existing_seeds:
            created = self._bootstrap_from_seed_rows(existing_seeds)
            self.logger.bootstrap_success(seed_path)
            return {"seed_path": str(seed_path), "imported": created}
        created = self._bootstrap_from_csv(seed_path)
        self.logger.bootstrap_success(seed_path)
        return {"seed_path": str(seed_path), "imported": created}

    def _bootstrap_from_seed_rows(self, seeds: list[dict[str, Any]]) -> int:
        """Replay persisted seed rows into the blog queue.

        Args:
            seeds: Durable seed payloads loaded from persistence.

        Returns:
            Number of newly inserted blog rows.
        """

        created = 0
        for seed in seeds:
            raw_url = str(seed.get("url") or "").strip()
            normalized_url = str(seed.get("normalized_url") or "").strip()
            domain = str(seed.get("domain") or "").strip()
            if not raw_url or not normalized_url or not domain:
                continue
            _, inserted = self.repository.upsert_blog(
                url=raw_url,
                normalized_url=normalized_url,
                domain=domain,
                accepted_by="seed",
                seed_source_path=seed.get("source_path"),
                seed_source_row=seed.get("source_row"),
            )
            created += int(inserted)
        return created

    def _bootstrap_from_csv(self, seed_path: Path) -> int:
        """Load fallback CSV seed rows into seeds and blogs.

        Args:
            seed_path: Filesystem path to the seed CSV file.

        Returns:
            Number of newly inserted blog rows.
        """

        created = 0
        with seed_path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row_number, row in enumerate(reader, start=2):
                raw_url = (row.get("url") or "").strip()
                if not raw_url:
                    continue
                normalized = normalize_url(raw_url)
                _, inserted = self.repository.upsert_blog(
                    url=raw_url,
                    normalized_url=normalized.normalized_url,
                    domain=normalized.domain,
                    accepted_by="seed",
                    seed_source_path=str(seed_path),
                    seed_source_row=row_number,
                )
                created += int(inserted)
        return created
