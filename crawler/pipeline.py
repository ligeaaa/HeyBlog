"""Orchestrate seed loading, crawl execution, and graph persistence."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Callable
from typing import Any

from crawler.discovery import discover_friend_links_pages
from crawler.extractor import ExtractedLink
from crawler.extractor import extract_candidate_links
from crawler.fetcher import FetchAttempt
from crawler.fetcher import Fetcher
from crawler.fetcher import FetchResult
from crawler.filters import decide_blog_candidate
from crawler.normalizer import normalize_url
from crawler.site_metadata import extract_site_metadata
from crawler.utils import unique_in_order
from crawler.export_service import ExportService
from persistence_api.repository import RepositoryProtocol
from shared.config import Settings


BlogStartHook = Callable[[dict[str, Any]], None]
BlogFinishHook = Callable[[dict[str, Any], dict[str, Any]], None]
BlogErrorHook = Callable[[dict[str, Any], Exception], None]
ShouldStopHook = Callable[[], bool]


class CrawlPipeline:
    """Coordinate one-shot crawl batches and seed bootstrapping."""

    def __init__(self, settings: Settings, repository: RepositoryProtocol) -> None:
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
                    source_blog_id=None,
                )
                created += int(inserted)
        self.repository.add_log(
            stage="bootstrap",
            result="success",
            message=f"Imported seeds from {path}",
        )
        return {"seed_path": str(path), "imported": created}

    def run_once(
        self,
        max_nodes: int | None = None,
        *,
        on_blog_start: BlogStartHook | None = None,
        on_blog_finish: BlogFinishHook | None = None,
        on_blog_error: BlogErrorHook | None = None,
        should_stop: ShouldStopHook | None = None,
    ) -> dict[str, Any]:
        """Run one crawl loop and export resulting graph snapshots."""
        processed = 0
        discovered = 0
        failed = 0
        limit = max_nodes or self.settings.max_nodes_per_run

        while processed < limit:
            if should_stop and should_stop():
                break
            blog = self.repository.get_next_waiting_blog()
            if blog is None:
                break
            if on_blog_start is not None:
                on_blog_start(dict(blog))
            processed += 1
            try:
                blog_result = self._crawl_blog(dict(blog))
                discovered += blog_result
                if on_blog_finish is not None:
                    on_blog_finish(dict(blog), {"discovered": blog_result})
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
                if on_blog_error is not None:
                    on_blog_error(dict(blog), exc)

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
        metadata = extract_site_metadata(homepage.url, homepage.text)

        # BFS step 1: homepage -> candidate friend-link pages.
        candidate_pages = self._discover_candidate_pages(homepage)

        # BFS step 2: fetch each candidate page -> extract -> filter -> store.
        discovered_count = self._crawl_candidate_pages(blog, candidate_pages)

        # BFS step 3: mark the current node as finished so the queue can continue.
        self._mark_blog_finished(
            blog_id=int(blog["id"]),
            status_code=homepage.status_code,
            discovered_count=discovered_count,
            blog_url=str(blog["url"]),
            title=metadata.title,
            icon_url=metadata.icon_url,
        )
        return discovered_count

    def _discover_candidate_pages(self, homepage: FetchResult) -> list[str]:
        """Return the candidate friend-link pages to visit for one homepage."""
        return unique_in_order(discover_friend_links_pages(homepage.url, homepage.text))

    def _crawl_candidate_pages(self, blog: dict[str, Any], candidate_pages: list[str]) -> int:
        """Fetch each candidate page and persist accepted child links."""
        discovered_count = 0
        seen_normalized: set[str] = set()
        page_attempts = self._fetch_candidate_pages(candidate_pages)

        for page_url in candidate_pages:
            page_attempt = page_attempts.get(page_url)
            if page_attempt is None or page_attempt.result is None:
                continue

            discovered_count += self._store_page_links(
                blog=blog,
                page=page_attempt.result,
                seen_normalized=seen_normalized,
            )

        return discovered_count

    def _fetch_candidate_pages(self, candidate_pages: list[str]) -> dict[str, FetchAttempt]:
        """Fetch candidate pages while preserving the original candidate ordering contract."""
        if not candidate_pages:
            return {}
        return self.fetcher.fetch_many(
            candidate_pages,
            max_concurrency=self.settings.candidate_page_fetch_concurrency,
        )

    def _store_page_links(
        self,
        *,
        blog: dict[str, Any],
        page: FetchResult,
        seen_normalized: set[str],
    ) -> int:
        """Persist accepted links extracted from one friend-link page."""
        stored_count = 0

        for link in extract_candidate_links(page.url, page.text):
            if not self._should_store_link(blog, link):
                continue

            normalized = normalize_url(link.url)
            if normalized.normalized_url in seen_normalized:
                continue
            seen_normalized.add(normalized.normalized_url)

            child_id, _ = self.repository.upsert_blog(
                url=link.url,
                normalized_url=normalized.normalized_url,
                domain=normalized.domain,
                source_blog_id=int(blog["id"]),
            )
            self.repository.add_edge(
                from_blog_id=int(blog["id"]),
                to_blog_id=child_id,
                link_url_raw=link.url,
                link_text=link.text,
            )
            stored_count += 1

        return stored_count

    def _should_store_link(self, blog: dict[str, Any], link: ExtractedLink) -> bool:
        """Return True when the extracted link survives deterministic filtering."""
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
        return decision.accepted

    def _mark_blog_finished(
        self,
        *,
        blog_id: int,
        status_code: int,
        discovered_count: int,
        blog_url: str,
        title: str | None,
        icon_url: str | None,
    ) -> None:
        """Persist the crawl result for one processed blog."""
        self.repository.mark_blog_result(
            blog_id=blog_id,
            crawl_status="FINISHED",
            status_code=status_code,
            friend_links_count=discovered_count,
            metadata_captured=True,
            title=title,
            icon_url=icon_url,
        )
        self.repository.add_log(
            blog_id=blog_id,
            stage="crawl",
            result="success",
            message=f"Crawled {blog_url}",
        )
