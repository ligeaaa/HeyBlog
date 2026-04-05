"""Seed bootstrap flow for the crawler."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from crawler.crawling.normalization import normalize_url
from crawler.observability.logger import CrawlerLogger
from persistence_api.repository import RepositoryProtocol


class BootstrapService:
    """Import crawler seed URLs into persistence."""

    def __init__(self, repository: RepositoryProtocol, logger: CrawlerLogger) -> None:
        self.repository = repository
        self.logger = logger

    def bootstrap_seeds(self, seed_path: Path) -> dict[str, Any]:
        """Import seed URLs from CSV into the blogs table."""
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
