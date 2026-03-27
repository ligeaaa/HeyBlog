"""Orchestrate seed loading, crawl execution, and graph persistence."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from app.config import Settings
from app.crawler.classifier import ClassifierUnavailableError
from app.crawler.classifier import build_classifier
from app.crawler.discovery import discover_friend_link_page_candidates
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
        classifier = build_classifier(self.settings)
        ranked_candidates = discover_friend_link_page_candidates(
            homepage.url,
            homepage.text,
            min_page_score=self.settings.friend_link_page_score_threshold,
        )
        candidate_pages = self._select_candidate_pages(ranked_candidates)
        discovered_count = 0
        seen_normalized: set[str] = set()

        for candidate_page in candidate_pages:
            try:
                page = self.fetcher.fetch(candidate_page.url)
            except Exception:  # noqa: BLE001
                continue

            extracted_links = extract_candidate_links(
                page.url,
                page.text,
                page_confidence=candidate_page.score,
                min_section_score=self.settings.friend_link_section_score_threshold,
            )
            classifier_decisions: dict[str, bool] = {}
            if (
                classifier is not None
                and candidate_page.score < self.settings.friend_link_ambiguity_threshold
                and extracted_links
            ):
                try:
                    reviewed = classifier.review_links(page.url, page.text, extracted_links)
                except ClassifierUnavailableError as exc:
                    self.repository.add_log(
                        blog_id=int(blog["id"]),
                        stage="classifier",
                        result="fallback",
                        message=str(exc),
                    )
                else:
                    if reviewed.available:
                        classifier_decisions = {
                            decision.url: decision.accepted for decision in reviewed.selected_links
                        }

            for link in extracted_links:
                decision_kwargs: dict[str, Any] = {
                    "link_text": link.text,
                    "context_text": link.context_text,
                    "section_score": link.section_score,
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
                if link.url in classifier_decisions and not classifier_decisions[link.url]:
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

    def _select_candidate_pages(self, ranked_candidates: list[Any]) -> list[Any]:
        """Pick high-confidence candidates first, then bounded fallbacks."""
        confident = [
            candidate
            for candidate in ranked_candidates
            if candidate.score >= self.settings.friend_link_page_score_threshold
        ]
        if confident:
            return confident[: self.settings.max_candidate_pages_per_blog]
        return ranked_candidates[: self.settings.max_path_probes_per_blog]
