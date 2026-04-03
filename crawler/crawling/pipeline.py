"""High-level crawler pipeline facade preserving the legacy API surface."""

from __future__ import annotations

from typing import Any
from typing import Callable

from crawler.contracts.results import CrawlRunStats
from crawler.crawling.bootstrap import BootstrapService
from crawler.crawling.decisions.chain import UrlDecisionChain
from crawler.crawling.decisions.rules import RuleBasedDecider
from crawler.crawling.fetching.httpx_fetcher import Fetcher
from crawler.crawling.orchestrator import CrawlOrchestrator
from crawler.domain.blog_node import BlogNode
from crawler.domain.crawl_state import CrawlState
from crawler.export_service import ExportService
from crawler.observability.logger import CrawlerLogger
from persistence_api.repository import RepositoryProtocol
from shared.config import Settings


BlogStartHook = Callable[[dict[str, Any]], None]
BlogFinishHook = Callable[[dict[str, Any], dict[str, Any]], None]
BlogErrorHook = Callable[[dict[str, Any], Exception], None]
ShouldStopHook = Callable[[], bool]


class CrawlPipeline:
    """Coordinate one-shot crawl batches and seed bootstrapping."""

    def __init__(self, settings: Settings, repository: RepositoryProtocol) -> None:
        self.settings = settings
        self.repository = repository
        self.logger = CrawlerLogger(repository)
        self.fetcher = Fetcher(
            user_agent=settings.user_agent,
            timeout_seconds=settings.request_timeout_seconds,
        )
        self.bootstrap_service = BootstrapService(repository, self.logger)
        self.export_service = ExportService(repository, settings.export_dir)
        self.orchestrator = self._build_orchestrator()

    def bootstrap_seeds(self, seed_path=None) -> dict[str, Any]:
        """Import seed URLs from CSV into the blogs table."""
        path = seed_path or self.settings.seed_path
        return self.bootstrap_service.bootstrap_seeds(path)

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
        stats = CrawlRunStats()
        limit = max_nodes or self.settings.max_nodes_per_run

        while stats.processed < limit:
            if should_stop and should_stop():
                break
            row = self.repository.get_next_waiting_blog()
            if row is None:
                break
            blog = BlogNode.from_row(row)
            if on_blog_start is not None:
                on_blog_start(blog.callback_payload())
            try:
                discovered = self._crawl_blog(blog.raw)
                stats.record_success(discovered)
                if on_blog_finish is not None:
                    on_blog_finish(blog.callback_payload(), {"discovered": discovered})
            except Exception as exc:  # noqa: BLE001
                self._mark_blog_failed(blog.id, exc)
                stats.record_failure()
                if on_blog_error is not None:
                    on_blog_error(blog.callback_payload(), exc)

        exports = self.export_service.write_exports()
        return {
            "processed": stats.processed,
            "discovered": stats.discovered,
            "failed": stats.failed,
            "exports": exports,
        }

    def _crawl_blog(self, blog: dict[str, Any]) -> int:
        """Crawl one blog and persist outgoing blog links."""
        self.orchestrator.fetcher = self.fetcher
        return self.orchestrator.crawl_blog(blog)

    def _mark_blog_failed(self, blog_id: int, error: Exception) -> None:
        """Persist the legacy failed-blog state and crawl log."""
        state = CrawlState(status="FAILED", status_code=None, friend_links_count=0)
        self.repository.mark_blog_result(
            blog_id=blog_id,
            crawl_status=state.status,
            status_code=state.status_code,
            friend_links_count=state.friend_links_count,
        )
        self.logger.crawl_error(blog_id=blog_id, error=error)

    def _build_orchestrator(self) -> CrawlOrchestrator:
        """Build the single-blog orchestrator bound to the current strategies."""
        decision_chain = UrlDecisionChain(
            steps=(
                RuleBasedDecider(
                    domain_blocklist=self.settings.friend_link_domain_blocklist,
                    blocked_tlds=self.settings.friend_link_tld_blocklist,
                    exact_url_blocklist=self.settings.friend_link_exact_url_blocklist,
                    prefix_blocklist=self.settings.friend_link_prefix_blocklist,
                ),
            )
        )
        return CrawlOrchestrator(
            settings=self.settings,
            repository=self.repository,
            fetcher=self.fetcher,
            decision_chain=decision_chain,
            logger=self.logger,
        )

