"""Single-blog crawl orchestration with explicit strategy seams."""

from __future__ import annotations

from time import monotonic

from crawler.contracts.results import BlogCrawlResult
from crawler.crawling.decisions.chain import UrlDecisionChain
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
    """Coordinate crawling one blog while preserving the existing persistence contract."""

    def __init__(
        self,
        *,
        settings: Settings,
        repository: RepositoryProtocol,
        fetcher: Fetcher,
        decision_chain: UrlDecisionChain,
        logger: CrawlerLogger,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.fetcher = fetcher
        self.decision_chain = decision_chain
        self.logger = logger

    def crawl_blog(self, blog: dict[str, object]) -> int:
        """Crawl one blog and persist outgoing blog links."""
        blog_record = BlogNode.from_row(blog)
        deadline = monotonic() + self.settings.blog_crawl_timeout_seconds
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
        """Return the candidate friend-link pages to visit for one homepage."""
        return unique_in_order(discover_friend_links_pages(homepage.url, homepage.text))

    def _crawl_candidate_pages(
        self,
        blog: BlogNode,
        candidate_pages: list[str],
        *,
        deadline: float,
    ) -> int:
        """Fetch each candidate page and persist accepted child links."""
        discovered_count = 0
        seen_normalized: set[str] = set()
        page_attempts = self._fetch_candidate_pages(candidate_pages, deadline=deadline, blog_url=blog.url)

        for page_url in candidate_pages:
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
        """Fetch candidate pages while preserving the original candidate ordering contract."""
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

    def _should_store_link(self, blog: BlogNode, link: ExtractedLink) -> bool:
        """Return True when the extracted link survives the configured decision chain."""
        decision = self.decision_chain.decide(
            link.url,
            blog.domain,
            link_text=link.text,
            context_text=link.context_text,
        )
        return decision.accepted

    def _mark_blog_finished(self, blog: BlogNode, result: BlogCrawlResult) -> None:
        """Persist the crawl result for one processed blog."""
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
        """Return the remaining crawl budget or raise once the per-blog deadline is exhausted."""
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"blog crawl timed out after {self.settings.blog_crawl_timeout_seconds:g} seconds: {blog_url}"
            )
        return remaining
