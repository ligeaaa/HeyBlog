"""Single-blog crawl orchestration with explicit strategy seams."""

from __future__ import annotations

from time import monotonic

from crawler.contracts.results import BlogCrawlResult
from crawler.crawling.decisions.base import UrlCandidateContext
from crawler.crawling.decisions.chain import ConfiguredUrlFilterChain
from crawler.crawling.discovery import discover_friend_links_pages
from crawler.crawling.extraction import ExtractedLink
from crawler.crawling.extraction import extract_candidate_links
from crawler.crawling.fetching.base import FetchAttempt
from crawler.crawling.fetching.base import FetchResult
from crawler.crawling.fetching.httpx_fetcher import Fetcher
from crawler.crawling.fetching.base import PageTooLargeError
from crawler.crawling.metadata import extract_site_metadata
from crawler.crawling.normalization import normalize_url
from crawler.domain.blog_node import BlogNode
from crawler.domain.crawl_state import CrawlState
from crawler.domain.friend_link_edge import FriendLinkEdge
from crawler.observability.logger import CrawlerLogger
from crawler.utils import unique_in_order
from persistence_api.repository import RepositoryProtocol
from shared.config import Settings


class CrawlOrchestrator:
    """Coordinate crawling one blog while preserving the persistence contract.

    Attributes:
        settings: Shared crawler settings controlling timeouts and concurrency.
        repository: Persistence boundary used to store discovered blogs and
        edges.
        fetcher: HTTP fetcher used for homepage and candidate-page requests.
        decision_chain: URL filtering chain that decides which extracted links
            represent blogs.
        logger: Logging facade used for success and error events.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        repository: RepositoryProtocol,
        fetcher: Fetcher,
        decision_chain: ConfiguredUrlFilterChain,
        logger: CrawlerLogger,
    ) -> None:
        """Store the strategy and infrastructure dependencies for blog crawling.

        Args:
            settings: Shared crawler configuration for timeout and concurrency
                behavior.
            repository: Persistence interface for blog and edge writes.
            fetcher: Fetch strategy used to retrieve HTML pages.
            decision_chain: Filtering strategy used on extracted links.
            logger: Logging facade for crawl lifecycle events.

        Returns:
            ``None``. The orchestrator stores the provided dependencies for
            later single-blog crawl operations.
        """
        self.settings = settings
        self.repository = repository
        self.fetcher = fetcher
        self.decision_chain = decision_chain
        self.logger = logger

    def crawl_blog(self, blog: dict[str, object]) -> int:
        """Crawl one blog homepage and persist accepted outbound blog links.

        Args:
            blog: Repository blog row describing the site that should be
                crawled.

        Returns:
            Number of accepted outbound blog links discovered for the blog.
        """
        blog_record = BlogNode.from_row(blog)
        deadline = monotonic() + self.settings.blog_crawl_timeout_seconds
        # The homepage drives all downstream work: metadata comes from it, and
        # candidate friend-link pages are discovered from it.
        homepage = self.fetcher.fetch(
            blog_record.url,
            timeout_seconds=self._remaining_timeout_seconds(deadline, blog_record.url),
        )
        metadata = extract_site_metadata(homepage.url, homepage.text)
        candidate_pages = self._discover_candidate_pages(homepage)
        discovered_count = self._crawl_candidate_pages(
            blog_record,
            candidate_pages,
            deadline=deadline,
        )
        self._remaining_timeout_seconds(deadline, blog_record.url)
        self._mark_blog_finished(
            blog_record,
            BlogCrawlResult(
                status_code=homepage.status_code,
                discovered_count=discovered_count,
                title=metadata.title,
                icon_url=metadata.icon_url,
            ),
        )
        return discovered_count

    def _discover_candidate_pages(self, homepage: FetchResult) -> list[str]:
        """Discover friend-link candidate pages starting from the homepage.

        Args:
            homepage: Successful homepage fetch result whose HTML should be
                inspected.

        Returns:
            Ordered unique candidate page URLs worth visiting for link
            extraction.
        """
        return unique_in_order(discover_friend_links_pages(homepage.url, homepage.text))

    def _crawl_candidate_pages(
        self,
        blog: BlogNode,
        candidate_pages: list[str],
        *,
        deadline: float,
    ) -> int:
        """Fetch candidate pages and persist accepted outbound blog links.

        Args:
            blog: Typed source blog being processed.
            candidate_pages: Candidate friend-link page URLs discovered from the
                homepage.
            deadline: Monotonic deadline for the entire per-blog crawl budget.

        Returns:
            Number of accepted outbound blog links stored for the blog.
        """
        discovered_count = 0
        seen_normalized: set[str] = set()
        page_attempts = self._fetch_candidate_pages(candidate_pages, deadline=deadline, blog_url=blog.url)

        for page_url in candidate_pages:
            # Iterate in original candidate order even though fetch_many() may
            # complete out of order; this keeps persistence deterministic.
            self._remaining_timeout_seconds(deadline, blog.url)
            page_attempt = page_attempts.get(page_url)
            if page_attempt is not None and page_attempt.error_kind == "page_too_large":
                raise PageTooLargeError(f"candidate page exceeded size limit: {page_url}")
            if page_attempt is None or page_attempt.result is None:
                continue
            discovered_count += self._store_page_links(
                blog=blog,
                page=page_attempt.result,
                seen_normalized=seen_normalized,
            )

        return discovered_count

    def _fetch_candidate_pages(
        self,
        candidate_pages: list[str],
        *,
        deadline: float,
        blog_url: str,
    ) -> dict[str, FetchAttempt]:
        """Fetch candidate pages while preserving the original request keys.

        Args:
            candidate_pages: Candidate page URLs to retrieve.
            deadline: Monotonic deadline shared by the whole blog crawl.
            blog_url: URL of the source blog, used only for timeout messages.

        Returns:
            Mapping from original candidate page URL to its fetch attempt
            outcome.
        """
        if not candidate_pages:
            return {}
        return self.fetcher.fetch_many(
            candidate_pages,
            max_concurrency=self.settings.candidate_page_fetch_concurrency,
            timeout_seconds=self._remaining_timeout_seconds(deadline, blog_url),
        )

    def _store_page_links(
        self,
        *,
        blog: BlogNode,
        page: FetchResult,
        seen_normalized: set[str],
    ) -> int:
        """Persist accepted extracted links from one fetched candidate page.

        Args:
            blog: Source blog whose candidate page is being processed.
            page: Successful fetched candidate page.
            seen_normalized: Set used to avoid persisting duplicate normalized
                child URLs across multiple candidate pages.

        Returns:
            Number of newly stored outbound blog links from the page.
        """
        stored_count = 0

        for link in extract_candidate_links(page.url, page.text):
            normalized = normalize_url(link.url)
            raw_record_id = self.repository.create_raw_discovered_url(
                source_blog_id=blog.id,
                normalized_url=normalized.normalized_url,
                status="pending",
            )
            status = self._evaluate_link_status(blog, normalized.normalized_url)
            self.repository.update_raw_discovered_url_status(record_id=raw_record_id, status=status)
            if status != "success":
                continue

            # Multiple friend-link pages often repeat the same target blog, so
            # de-duplicate on normalized URL before creating blogs or edges.
            if normalized.normalized_url in seen_normalized:
                continue
            seen_normalized.add(normalized.normalized_url)

            child_id, _ = self.repository.upsert_blog(
                url=link.url,
                normalized_url=normalized.normalized_url,
                domain=normalized.domain,
            )
            edge = FriendLinkEdge(
                from_blog_id=blog.id,
                to_blog_id=child_id,
                link_url_raw=link.url,
                link_text=link.text,
            )
            self.repository.add_edge(
                from_blog_id=edge.from_blog_id,
                to_blog_id=edge.to_blog_id,
                link_url_raw=edge.link_url_raw,
                link_text=edge.link_text,
            )
            stored_count += 1

        return stored_count

    def _evaluate_link_status(self, blog: BlogNode, normalized_url: str) -> str:
        """Return the final filter-chain status for one normalized candidate URL.

        Args:
            blog: Source blog currently being crawled.
            normalized_url: Normalized candidate URL extracted from a friend-link page.

        Returns:
            The final status emitted by the configured filter chain.
        """
        decision = self.decision_chain.evaluate(
            UrlCandidateContext(
                source_blog_id=blog.id,
                source_domain=blog.domain,
                normalized_url=normalized_url,
            )
        )
        return str(decision.status or "success")

    def _mark_blog_finished(self, blog: BlogNode, result: BlogCrawlResult) -> None:
        """Persist the final crawl result for one processed blog.

        Args:
            blog: Source blog whose crawl completed successfully.
            result: Typed crawl result including metadata and discovered counts.

        Returns:
            ``None``. Repository state and logs are updated in place.
        """
        state = CrawlState(
            status="FINISHED",
            status_code=result.status_code,
            friend_links_count=result.discovered_count,
            metadata_captured=True,
            title=result.title,
            icon_url=result.icon_url,
        )
        self.repository.mark_blog_result(
            blog_id=blog.id,
            crawl_status=state.status,
            status_code=state.status_code,
            friend_links_count=state.friend_links_count,
            metadata_captured=state.metadata_captured,
            title=state.title,
            icon_url=state.icon_url,
        )
        self.logger.crawl_success(blog_id=blog.id, blog_url=blog.url)

    def _remaining_timeout_seconds(self, deadline: float, blog_url: str) -> float:
        """Return remaining crawl budget or raise when the deadline is exhausted.

        Args:
            deadline: Monotonic deadline timestamp for the current blog crawl.
            blog_url: Source blog URL used in timeout error messages.

        Returns:
            Remaining allowed seconds for this blog crawl.

        Raises:
            TimeoutError: If the per-blog crawl deadline has already expired.
        """
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"blog crawl timed out after {self.settings.blog_crawl_timeout_seconds:g} seconds: {blog_url}"
            )
        return remaining
