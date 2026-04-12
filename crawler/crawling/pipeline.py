"""High-level crawler pipeline facade preserving the legacy API surface."""

from __future__ import annotations

from typing import Any
from typing import Callable

from crawler.contracts.results import CrawlRunStats
from crawler.crawling.bootstrap import BootstrapService
from crawler.crawling.decisions.chain import build_url_decision_chain
from crawler.crawling.fetching.base import PageTooLargeError
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
    """Coordinate seed bootstrap, one-shot crawl batches, and export writing.

    Attributes:
        settings: Shared crawler settings controlling fetch, queue, and export
            behavior.
        repository: Persistence boundary used to claim blogs and store results.
        logger: Logging facade for crawl lifecycle events.
        fetcher: Long-lived HTTP fetcher reused across blog crawls.
        bootstrap_service: Service responsible for importing seed URLs.
        export_service: Service responsible for writing graph exports.
        orchestrator: Per-blog crawl coordinator used by the batch loop.
    """

    def __init__(self, settings: Settings, repository: RepositoryProtocol) -> None:
        """Build the one-shot crawl pipeline and its strategy dependencies.

        Args:
            settings: Shared crawler configuration for fetch and scheduling
                behavior.
            repository: Persistence interface used by the pipeline and
                orchestrator.

        Returns:
            ``None``. The pipeline stores its dependencies and builds the
            helper services required for crawl execution.
        """
        self.settings = settings
        self.repository = repository
        self.logger = CrawlerLogger()
        self.fetcher = Fetcher(
            user_agent=settings.user_agent,
            timeout_seconds=settings.request_timeout_seconds,
            max_page_bytes=settings.max_fetched_page_bytes,
        )
        self.bootstrap_service = BootstrapService(repository, self.logger)
        self.export_service = ExportService(repository, settings.export_dir)
        self.orchestrator = self._build_orchestrator()

    def bootstrap_seeds(self, seed_path=None) -> dict[str, Any]:
        """Import seed URLs into persistence using the bootstrap service.

        Args:
            seed_path: Optional override path to the seed CSV file. When not
                provided, the configured default seed path is used.

        Returns:
            Bootstrap result payload returned by ``BootstrapService``.
        """
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
        """Run one synchronous crawl batch and then write graph exports.

        Args:
            max_nodes: Optional maximum number of blogs to process in this run.
                When omitted, the configured batch size is used.
            on_blog_start: Optional callback invoked when a claimed blog begins
                processing.
            on_blog_finish: Optional callback invoked after a blog completes
                successfully.
            on_blog_error: Optional callback invoked after a blog fails.
            should_stop: Optional callback checked between claims so callers can
                end the batch gracefully.

        Returns:
            A result payload containing processed, discovered, failed, and
            export counts for the completed batch.
        """
        stats = CrawlRunStats()
        limit = max_nodes or self.settings.max_nodes_per_run
        normal_slots_remaining = 0

        while stats.processed < limit:
            if should_stop and should_stop():
                break
            # Claiming and processing stay in one loop so the batch result
            # always reflects the same queue-fairness rules as runtime mode.
            row, _claimed_priority, normal_slots_remaining = self._claim_next_scheduled_blog(
                normal_slots_remaining=normal_slots_remaining
            )
            if row is None:
                break
            result = self.process_blog_row(
                row,
                on_blog_start=on_blog_start,
                on_blog_finish=on_blog_finish,
                on_blog_error=on_blog_error,
            )
            stats.processed += int(result["processed"])
            stats.discovered += int(result["discovered"])
            stats.failed += int(result["failed"])

        exports = self.write_exports()
        return {
            "processed": stats.processed,
            "discovered": stats.discovered,
            "failed": stats.failed,
            "exports": exports,
        }

    def process_blog_row(
        self,
        row: dict[str, Any],
        *,
        on_blog_start: BlogStartHook | None = None,
        on_blog_finish: BlogFinishHook | None = None,
        on_blog_error: BlogErrorHook | None = None,
    ) -> dict[str, int]:
        """Process one already-claimed repository row.

        Args:
            row: Repository blog row that has already been claimed for crawling.
            on_blog_start: Optional callback invoked just before crawl work
                begins.
            on_blog_finish: Optional callback invoked after a successful crawl.
            on_blog_error: Optional callback invoked after a failed crawl.

        Returns:
            A small result payload describing whether one blog was processed,
            how many child links were discovered, and whether the attempt
            failed.
        """
        blog = BlogNode.from_row(row)
        if hasattr(self.repository, "mark_ingestion_request_crawling"):
            # Priority ingestion requests need a state transition before the
            # actual crawl starts so UI callers can observe progress promptly.
            self.repository.mark_ingestion_request_crawling(blog_id=blog.id)
        if on_blog_start is not None:
            on_blog_start(blog.callback_payload())
        try:
            discovered = self._crawl_blog(blog.raw)
            if on_blog_finish is not None:
                on_blog_finish(blog.callback_payload(), {"discovered": discovered})
            return {"processed": 1, "discovered": discovered, "failed": 0}
        except Exception as exc:  # noqa: BLE001
            self._mark_blog_failed(blog.id, exc)
            if on_blog_error is not None:
                on_blog_error(blog.callback_payload(), exc)
            return {"processed": 1, "discovered": 0, "failed": 1}

    def write_exports(self) -> dict[str, Any]:
        """Write export artifacts for the current repository graph state.

        Returns:
            Export file paths returned by ``ExportService``.
        """
        return self.export_service.write_exports()

    def _claim_next_scheduled_blog(self, *, normal_slots_remaining: int) -> tuple[dict[str, Any] | None, bool, int]:
        """Claim the next eligible blog while enforcing priority fairness.

        Args:
            normal_slots_remaining: Remaining count in the current fairness
                window that allows normal-queue blogs after a priority claim.

        Returns:
            A tuple of ``(row, claimed_priority, next_normal_slots_remaining)``
            describing the claimed blog, whether it came from the priority
            queue, and the updated fairness-window counter.
        """
        priority_slots = max(1, self.settings.priority_seed_normal_queue_slots)
        if normal_slots_remaining <= 0:
            # A priority seed wins immediately when its turn comes up.
            row = self._get_next_priority_blog()
            if row is not None:
                return row, True, priority_slots

        include_priority = normal_slots_remaining <= 0
        row = self._get_next_waiting_blog(include_priority=include_priority)
        if row is not None:
            # After one priority seed is claimed, let a bounded number of normal
            # queue items run before checking the priority queue again.
            next_remaining = max(0, normal_slots_remaining - 1) if normal_slots_remaining > 0 else 0
            return row, False, next_remaining

        if normal_slots_remaining > 0:
            # If the normal queue is empty during a fairness window, do not make
            # the priority seed wait for the remaining normal slots to expire.
            row = self._get_next_priority_blog()
            if row is not None:
                return row, True, priority_slots
        return None, False, 0

    def _get_next_priority_blog(self) -> dict[str, Any] | None:
        """Return the next priority blog row if the repository supports it.

        Returns:
            The claimed priority blog row, or ``None`` when no priority queue is
            available or no priority blog is waiting.
        """
        getter = getattr(self.repository, "get_next_priority_blog", None)
        if getter is None:
            return None
        return getter()

    def _get_next_waiting_blog(self, *, include_priority: bool) -> dict[str, Any] | None:
        """Return the next waiting blog row from the main queue.

        Args:
            include_priority: Whether repository implementations should allow
                priority rows to be returned from the general waiting query.

        Returns:
            The next claimed waiting blog row, or ``None`` when the queue is
            empty.
        """
        getter = self.repository.get_next_waiting_blog
        try:
            return getter(include_priority=include_priority)
        except TypeError:
            return getter()

    def _crawl_blog(self, blog: dict[str, Any]) -> int:
        """Crawl one blog row through the orchestrator.

        Args:
            blog: Repository blog row that should be crawled.

        Returns:
            Number of accepted outbound blog links discovered for the blog.
        """
        # The pipeline owns the long-lived fetcher so tests and runtime callers
        # can replace it once and still hit the orchestrator path consistently.
        self.orchestrator.fetcher = self.fetcher
        return self.orchestrator.crawl_blog(blog)

    def _mark_blog_failed(self, blog_id: int, error: Exception) -> None:
        """Persist a failed crawl result for one blog.

        Args:
            blog_id: Identifier of the failed blog.
            error: Exception raised while processing the blog.

        Returns:
            ``None``. The repository state and crawl log are updated in place.
        """
        status_code = 413 if isinstance(error, PageTooLargeError) else None
        state = CrawlState(status="FAILED", status_code=status_code, friend_links_count=0)
        self.repository.mark_blog_result(
            blog_id=blog_id,
            crawl_status=state.status,
            status_code=state.status_code,
            friend_links_count=state.friend_links_count,
        )
        self.logger.crawl_error(blog_id=blog_id, error=error)

    def _build_orchestrator(self) -> CrawlOrchestrator:
        """Build the single-blog orchestrator bound to current strategies.

        Returns:
            A configured ``CrawlOrchestrator`` using the current fetcher,
            repository, settings, logger, and URL-decision chain.
        """
        decision_chain = build_url_decision_chain(self.settings)
        return CrawlOrchestrator(
            settings=self.settings,
            repository=self.repository,
            fetcher=self.fetcher,
            decision_chain=decision_chain,
            logger=self.logger,
        )
