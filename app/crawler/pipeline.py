"""Orchestrate seed loading, crawl execution, and graph persistence."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from app.config import Settings
from app.crawler.discovery import discover_friend_links_pages
from app.crawler.extractor import extract_candidate_links
from app.crawler.fetcher import Fetcher
from app.crawler.filters import decide_blog_candidate
from app.crawler.normalizer import normalize_url
from app.db.repository import Repository
from app.services.export_service import ExportService


class CrawlPipeline:
    """Coordinate one-shot crawl batches and seed bootstrapping."""

    def __init__(self, settings: Settings, repository: Repository) -> None:
        """Initialize dependencies required for crawl operations."""
        self.settings = settings
        self.repository = repository
        self.fetcher = Fetcher(
            user_agent=settings.user_agent,
            timeout_seconds=settings.request_timeout_seconds,
        )
        self.export_service = ExportService(repository, settings.export_dir)

    def bootstrap_seeds(self, seed_path: Path | None = None) -> dict[str, Any]:
        """Import seed URLs from CSV into the blogs table."""
        path = seed_path or self.settings.seed_path
        created = 0
        with path.open("r", encoding="utf-8") as handle:
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
                    depth=0,
                    source_blog_id=None,
                )
                created += int(inserted)
        self.repository.add_log(
            stage="bootstrap",
            result="success",
            message=f"Imported seeds from {path}",
        )
        return {"seed_path": str(path), "imported": created}

    def run_once(self, max_nodes: int | None = None) -> dict[str, Any]:
        """Run one crawl loop and export resulting graph snapshots."""
        processed = 0
        discovered = 0
        failed = 0
        limit = max_nodes or self.settings.max_nodes_per_run

        while processed < limit:
            blog = self.repository.get_next_waiting_blog(self.settings.max_depth)
            if blog is None:
                break
            processed += 1
            try:
                discovered += self._crawl_blog(dict(blog))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                self.repository.mark_blog_result(
                    blog_id=int(blog["id"]),
                    crawl_status="FAILED",
                    status_code=None,
                    friend_links_count=0,
                )
                self.repository.add_log(
                    blog_id=int(blog["id"]),
                    stage="crawl",
                    result="error",
                    message=str(exc),
                )

        exports = self.export_service.write_exports()
        return {
            "processed": processed,
            "discovered": discovered,
            "failed": failed,
            "exports": exports,
        }

    def _crawl_blog(self, blog: dict[str, Any]) -> int:
        """Crawl one blog and persist outgoing blog links."""
        homepage = self.fetcher.fetch(str(blog["url"]))
        candidate_pages = discover_friend_links_pages(homepage.url, homepage.text)
        candidate_pages = candidate_pages[: self.settings.max_candidate_pages_per_blog]

        discovered_count = 0
        seen_normalized: set[str] = set()

        for page_url in candidate_pages:
            try:
                page = self.fetcher.fetch(page_url)
            except Exception:  # noqa: BLE001
                continue

            for link in extract_candidate_links(page.url, page.text):
                decision_kwargs: dict[str, Any] = {
                    "link_text": link.text,
                    "context_text": link.context_text,
                    "domain_blocklist": self.settings.friend_link_domain_blocklist,
                    "exact_url_blocklist": self.settings.friend_link_exact_url_blocklist,
                    "prefix_blocklist": self.settings.friend_link_prefix_blocklist,
                }
                if self.settings.friend_link_tld_blocklist:
                    decision_kwargs["blocked_tlds"] = self.settings.friend_link_tld_blocklist
                decision = decide_blog_candidate(
                    link.url,
                    str(blog["domain"]),
                    **decision_kwargs,
                )
                if not decision.accepted:
                    continue
                normalized = normalize_url(link.url)
                if normalized.normalized_url in seen_normalized:
                    continue
                seen_normalized.add(normalized.normalized_url)
                child_id, _ = self.repository.upsert_blog(
                    url=link.url,
                    normalized_url=normalized.normalized_url,
                    domain=normalized.domain,
                    depth=int(blog["depth"]) + 1,
                    source_blog_id=int(blog["id"]),
                )
                self.repository.add_edge(
                    from_blog_id=int(blog["id"]),
                    to_blog_id=child_id,
                    link_url_raw=link.url,
                    link_text=link.text,
                )
                discovered_count += 1
                if discovered_count >= self.settings.max_outgoing_links_per_blog:
                    break
            if discovered_count >= self.settings.max_outgoing_links_per_blog:
                break

        self.repository.mark_blog_result(
            blog_id=int(blog["id"]),
            crawl_status="FINISHED",
            status_code=homepage.status_code,
            friend_links_count=discovered_count,
        )
        self.repository.add_log(
            blog_id=int(blog["id"]),
            stage="crawl",
            result="success",
            message=f"Crawled {blog['url']}",
        )
        return discovered_count
