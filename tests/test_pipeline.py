"""Integration-style tests for the crawl pipeline discovery flow."""

from pathlib import Path
from typing import Any
from typing import Callable

import pytest
from sqlalchemy import select

from crawler.crawling.fetching.base import FetchAttempt
from crawler.crawling.fetching.base import FetchResult
from crawler.crawling.pipeline import CrawlPipeline
from persistence_api.db import session_scope
from persistence_api.models import BlogModel
from persistence_api.models import RawDiscoveredUrlModel
from persistence_api.repository import Repository
from shared.config import Settings


class FakeFetcher:
    """Return pre-baked fetch responses for pipeline tests."""

    def __init__(
        self,
        responses: dict[str, FetchResult],
        *,
        batch_results: dict[str, FetchAttempt] | None = None,
        on_fetch: Callable[[str, float | None], None] | None = None,
        on_fetch_many: Callable[[list[str], float | None], None] | None = None,
        valid_icon_urls: dict[str, str | None] | None = None,
    ) -> None:
        self.responses = responses
        self.batch_results = batch_results or {}
        self.on_fetch = on_fetch
        self.on_fetch_many = on_fetch_many
        self.calls: list[str] = []
        self.fetch_timeouts: list[float | None] = []
        self.fetch_many_calls: list[tuple[list[str], int, float | None]] = []
        self.batch_completion_order: list[str] = []
        self.valid_icon_urls = valid_icon_urls or {}
        self.icon_validation_calls: list[tuple[str, float | None]] = []

    def fetch(self, url: str, *, timeout_seconds: float | None = None) -> FetchResult:
        self.calls.append(url)
        self.fetch_timeouts.append(timeout_seconds)
        if self.on_fetch is not None:
            self.on_fetch(url, timeout_seconds)
        return self.responses[url]

    def fetch_many(
        self,
        urls: list[str],
        *,
        max_concurrency: int,
        timeout_seconds: float | None = None,
    ) -> dict[str, FetchAttempt]:
        self.fetch_many_calls.append((list(urls), max_concurrency, timeout_seconds))
        if self.on_fetch_many is not None:
            self.on_fetch_many(urls, timeout_seconds)
        if self.batch_results:
            self.batch_completion_order.extend(list(self.batch_results))
            attempts = {
                url: self.batch_results[url]
                for url in self.batch_results
                if url in urls
            }
            for url in urls:
                attempts.setdefault(
                    url,
                    FetchAttempt(request_url=url, result=None, error_kind="request_error"),
                )
            return attempts

        return {
            url: FetchAttempt(
                request_url=url,
                result=self.responses.get(url),
                error_kind=None if url in self.responses else "request_error",
            )
            for url in urls
        }

    def validate_icon_url(self, url: str, *, timeout_seconds: float | None = None) -> str | None:
        self.icon_validation_calls.append((url, timeout_seconds))
        return self.valid_icon_urls.get(url)


def build_pipeline(tmp_path: Path) -> tuple[CrawlPipeline, Repository]:
    """Construct a pipeline backed by a temporary repository."""
    settings = Settings(
        db_path=tmp_path / "db.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        max_path_probes_per_blog=2,
        candidate_page_fetch_concurrency=4,
        decision_model_consensus_enabled=False,
    )
    repository = Repository(settings.db_path)
    pipeline = CrawlPipeline(settings, repository)
    return pipeline, repository


def seed_blog(repository: Repository) -> dict[str, Any]:
    """Insert and return a standard seed blog row."""
    blog_id, _ = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
    )
    blog = repository.get_blog(blog_id)
    assert blog is not None
    return blog


def test_pipeline_persists_only_valid_friend_links(tmp_path: Path) -> None:
    """Only validated friend links from extracted sections should become edges."""
    pipeline, repository = build_pipeline(tmp_path)
    blog = seed_blog(repository)

    homepage_html = """
    <html>
      <body>
        <footer><a href="/friends">友情链接</a></footer>
      </body>
    </html>
    """
    friend_page_html = """
    <html>
      <body>
        <section class="friend-links">
          <h2>友情链接</h2>
          <ul>
            <li><a href="https://friend.example/">Friend</a></li>
            <li><a href="https://github.com/example">GitHub</a></li>
            <li><a href="https://agency.gov/">Agency</a></li>
          </ul>
        </section>
      </body>
    </html>
    """
    pipeline.fetcher = FakeFetcher(
        {
            "https://blog.example.com/": FetchResult(
                url="https://blog.example.com/",
                status_code=200,
                text=homepage_html,
            ),
            "https://blog.example.com/friends": FetchResult(
                url="https://blog.example.com/friends",
                status_code=200,
                text=friend_page_html,
            ),
        },
        valid_icon_urls={
            "https://blog.example.com/static/favicon.png": "https://cdn.example.com/favicon.png",
        },
    )

    discovered = pipeline._crawl_blog(blog)

    assert discovered == 1
    edges = repository.list_edges()
    assert len(edges) == 1
    assert edges[0]["link_url_raw"] == "https://friend.example/"

    with session_scope(repository.session_factory) as session:
        raw_rows = [
            (row.source_blog_id, row.normalized_url, row.status, row.accepted_by)
            for row in session.query(RawDiscoveredUrlModel).order_by(RawDiscoveredUrlModel.id.asc()).all()
        ]

    assert [source_blog_id for source_blog_id, _, _, _ in raw_rows] == [blog["blog_id"], blog["blog_id"], blog["blog_id"]]
    assert [normalized_url for _, normalized_url, _, _ in raw_rows] == [
        "https://friend.example/",
        "https://github.com/example",
        "https://agency.gov/",
    ]
    assert [status for _, _, status, _ in raw_rows] == [
        "success",
        "rule:platform_blocked",
        "rule:blocked_tld",
    ]
    blogs = repository.list_blogs()
    assert len(blogs) == 2
    child_blog = next(blog_row for blog_row in blogs if blog_row["id"] != blog["id"])
    assert child_blog["domain"] == "friend.example"
    assert "depth" not in child_blog


def test_pipeline_persists_edges_for_duplicate_target_urls(tmp_path: Path) -> None:
    """Repeated target URL discoveries should still preserve new source edges."""
    pipeline, repository = build_pipeline(tmp_path)
    alpha = seed_blog(repository)
    beta_id, _ = repository.upsert_blog(
        url="https://beta.example/",
        normalized_url="https://beta.example/",
        domain="beta.example",
    )
    beta = repository.get_blog(beta_id)
    assert beta is not None

    homepage_html = '<html><body><footer><a href="/friends">友情链接</a></footer></body></html>'
    alpha_friend_page_html = """
    <html><body><section class="friend-links">
      <a href="https://common.example/">Common</a>
    </section></body></html>
    """
    beta_friend_page_html = """
    <html><body><section class="friend-links">
      <a href="https://common.example/">Common Again</a>
      <a href="https://common.example/">Common Duplicate</a>
    </section></body></html>
    """
    pipeline.fetcher = FakeFetcher(
        {
            "https://blog.example.com/": FetchResult(
                url="https://blog.example.com/",
                status_code=200,
                text=homepage_html,
            ),
            "https://blog.example.com/friends": FetchResult(
                url="https://blog.example.com/friends",
                status_code=200,
                text=alpha_friend_page_html,
            ),
            "https://beta.example/": FetchResult(
                url="https://beta.example/",
                status_code=200,
                text=homepage_html,
            ),
            "https://beta.example/friends": FetchResult(
                url="https://beta.example/friends",
                status_code=200,
                text=beta_friend_page_html,
            ),
        }
    )

    assert pipeline._crawl_blog(alpha) == 1
    assert pipeline._crawl_blog(beta) == 1

    common_blog = next(blog for blog in repository.list_blogs() if blog["domain"] == "common.example")
    edges = repository.list_edges()
    assert {(edge["from_blog_id"], edge["to_blog_id"]) for edge in edges} == {
        (alpha["blog_id"], common_blog["id"]),
        (beta["blog_id"], common_blog["id"]),
    }

    with session_scope(repository.session_factory) as session:
        raw_rows = [
            (row.source_blog_id, row.normalized_url, row.status)
            for row in session.scalars(select(RawDiscoveredUrlModel).order_by(RawDiscoveredUrlModel.id.asc()))
        ]

    assert raw_rows == [
        (alpha["blog_id"], "https://common.example/", "success"),
        (beta["blog_id"], "https://common.example/", "rule:duplicate_url"),
    ]


def test_pipeline_stores_feed_url_when_friend_link_exposes_rss(tmp_path: Path) -> None:
    """A friend link whose homepage exposes a valid feed should persist its feed URL."""
    pipeline, repository = build_pipeline(tmp_path)
    blog = seed_blog(repository)

    homepage_html = '<html><body><footer><a href="/friends">友情链接</a></footer></body></html>'
    friend_page_html = """
    <html>
      <body>
        <section class="friend-links">
          <h2>友情链接</h2>
          <ul><li><a href="https://friend.example/">Friend</a></li></ul>
        </section>
      </body>
    </html>
    """
    friend_homepage_html = (
        '<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml">'
        "</head><body>hi</body></html>"
    )
    valid_feed = (
        '<?xml version="1.0"?><rss version="2.0"><channel>'
        "<title>Friend Blog</title><item><title>Post</title></item></channel></rss>"
    )
    pipeline.fetcher = FakeFetcher(
        {
            "https://blog.example.com/": FetchResult(
                url="https://blog.example.com/", status_code=200, text=homepage_html
            ),
            "https://blog.example.com/friends": FetchResult(
                url="https://blog.example.com/friends", status_code=200, text=friend_page_html
            ),
            "https://friend.example/": FetchResult(
                url="https://friend.example/", status_code=200, text=friend_homepage_html
            ),
            "https://friend.example/feed.xml": FetchResult(
                url="https://friend.example/feed.xml", status_code=200, text=valid_feed
            ),
        }
    )

    discovered = pipeline._crawl_blog(blog)

    assert discovered == 1
    blogs = repository.list_blogs_catalog(page_size=50)["items"]
    child_blog = next(row for row in blogs if row["domain"] == "friend.example")
    assert child_blog["feed_url"] == "https://friend.example/feed.xml"
    with session_scope(repository.session_factory) as session:
        raw = session.scalar(
            select(RawDiscoveredUrlModel).where(RawDiscoveredUrlModel.normalized_url == "https://friend.example/")
        )
        raw_status = None if raw is None else raw.status
        raw_accepted_by = None if raw is None else raw.accepted_by
    assert raw is not None
    assert raw_status == "success"
    assert raw_accepted_by == "rss"


def test_pipeline_stops_before_claim_when_raw_discovered_url_limit_is_reached(tmp_path: Path) -> None:
    """One-shot crawl batches should refuse new claims once raw URL volume reaches the limit."""
    pipeline, repository = build_pipeline(tmp_path)
    pipeline.settings.raw_discovered_url_limit = 1
    pipeline.capacity_gate.raw_discovered_url_limit = 1
    blog = seed_blog(repository)
    repository.create_raw_discovered_url(
        source_blog_id=blog["blog_id"],
        normalized_url="https://existing.example/",
        status="success",
    )
    pipeline.fetcher = FakeFetcher(
        {
            "https://blog.example.com/": FetchResult(
                url="https://blog.example.com/",
                status_code=200,
                text="<html><body></body></html>",
            ),
        }
    )

    result = pipeline.run_once(max_nodes=1)

    assert result["processed"] == 0
    assert result["stop_reason"] == "raw_discovered_url_limit_reached"
    assert pipeline.fetcher.calls == []


def test_pipeline_persists_site_title_and_icon_metadata(tmp_path: Path) -> None:
    """Homepage crawl should persist title and icon metadata onto the source blog."""
    pipeline, repository = build_pipeline(tmp_path)
    blog = seed_blog(repository)

    homepage_html = """
    <html>
      <head>
        <title>Alpha Blog</title>
        <link rel="icon" href="/static/favicon.png" />
      </head>
      <body>
        <footer><a href="/friends">友情链接</a></footer>
      </body>
    </html>
    """
    friend_page_html = """
    <html><body><section><h2>友情链接</h2>
      <a href="https://friend.example/">Friend</a>
    </section></body></html>
    """
    pipeline.fetcher = FakeFetcher(
        {
            "https://blog.example.com/": FetchResult(
                url="https://blog.example.com/",
                status_code=200,
                text=homepage_html,
            ),
            "https://blog.example.com/friends": FetchResult(
                url="https://blog.example.com/friends",
                status_code=200,
                text=friend_page_html,
            ),
        },
        valid_icon_urls={
            "https://blog.example.com/static/favicon.png": "https://cdn.example.com/favicon.png",
        },
    )

    pipeline._crawl_blog(blog)

    refreshed = repository.get_blog(int(blog["id"]))
    assert refreshed is not None
    assert refreshed["title"] == "Alpha Blog"
    assert refreshed["icon_url"] == "https://cdn.example.com/favicon.png"
    assert pipeline.fetcher.icon_validation_calls[0][0] == "https://blog.example.com/static/favicon.png"


def test_pipeline_keeps_icon_null_when_page_has_no_icon_link(tmp_path: Path) -> None:
    """Missing explicit icon markup should leave persisted icon metadata empty."""
    pipeline, repository = build_pipeline(tmp_path)
    blog = seed_blog(repository)

    pipeline.fetcher = FakeFetcher(
        {
            "https://blog.example.com/": FetchResult(
                url="https://blog.example.com/",
                status_code=200,
                text="<html><head><title>Plain Blog</title></head><body></body></html>",
            ),
        }
    )

    pipeline._crawl_blog(blog)

    refreshed = repository.get_blog(int(blog["id"]))
    assert refreshed is not None
    assert refreshed["title"] == "Plain Blog"
    assert refreshed["icon_url"] is None
    with session_scope(repository.session_factory) as session:
        stored_icon_url = session.scalar(select(BlogModel.icon_url).where(BlogModel.blog_id == int(blog["id"])))
    assert stored_icon_url is None
    assert pipeline.fetcher.icon_validation_calls == []


def test_pipeline_keeps_icon_null_when_icon_validation_fails(tmp_path: Path) -> None:
    """Unreachable extracted icon candidates should not be persisted."""
    pipeline, repository = build_pipeline(tmp_path)
    blog = seed_blog(repository)

    pipeline.fetcher = FakeFetcher(
        {
            "https://blog.example.com/": FetchResult(
                url="https://blog.example.com/",
                status_code=200,
                text=(
                    "<html><head><title>Plain Blog</title>"
                    '<link rel="icon" href="/missing.ico" />'
                    "</head><body></body></html>"
                ),
            ),
        },
        valid_icon_urls={"https://blog.example.com/missing.ico": None},
    )

    pipeline._crawl_blog(blog)

    refreshed = repository.get_blog(int(blog["id"]))
    assert refreshed is not None
    assert refreshed["title"] == "Plain Blog"
    assert refreshed["icon_url"] is None
    with session_scope(repository.session_factory) as session:
        stored_icon_url = session.scalar(select(BlogModel.icon_url).where(BlogModel.blog_id == int(blog["id"])))
    assert stored_icon_url is None
    assert pipeline.fetcher.icon_validation_calls[0][0] == "https://blog.example.com/missing.ico"


def test_pipeline_enqueues_discovered_children_without_depth_gating(tmp_path: Path) -> None:
    """Crawler should persist discovered children without any depth-based suppression."""
    pipeline, repository = build_pipeline(tmp_path)
    blog = seed_blog(repository)

    pipeline.fetcher = FakeFetcher(
        {
            "https://blog.example.com/": FetchResult(
                url="https://blog.example.com/",
                status_code=200,
                text="""
                <html>
                  <body>
                    <footer><a href="/friends">友情链接</a></footer>
                  </body>
                </html>
                """,
            ),
            "https://blog.example.com/friends": FetchResult(
                url="https://blog.example.com/friends",
                status_code=200,
                text="""
                <html><body><section><h2>友情链接</h2>
                  <a href="https://friend.example/">Friend</a>
                </section></body></html>
                """,
            ),
        }
    )

    discovered = pipeline._crawl_blog(blog)

    assert discovered == 1
    edges = repository.list_edges()
    assert len(edges) == 1
    blogs = repository.list_blogs()
    assert len(blogs) == 2
    assert blogs[1]["domain"] == "friend.example"
    assert blogs[1]["crawl_status"] == "WAITING"


def test_pipeline_uses_fallback_paths_when_homepage_has_no_friend_link_entry(tmp_path: Path) -> None:
    """Pipeline should still try fallback friend-link paths when homepage gives no signal."""
    pipeline, repository = build_pipeline(tmp_path)
    blog = seed_blog(repository)

    pipeline.fetcher = FakeFetcher(
        {
            "https://blog.example.com/": FetchResult(
                url="https://blog.example.com/",
                status_code=200,
                text="<html><body><a href='/about'>About</a></body></html>",
            ),
            "https://blog.example.com/links": FetchResult(
                url="https://blog.example.com/links",
                status_code=200,
                text="""
                <html><body><section><h2>友情链接</h2>
                <a href='https://friend.example/'>Friend</a>
                <a href='https://friend-two.example/'>Friend Two</a>
                <a href='https://friend-three.example/'>Friend Three</a>
                </section></body></html>
                """,
            ),
        }
    )

    discovered = pipeline._crawl_blog(blog)

    assert discovered == 3



def test_pipeline_deduplicates_normalized_child_links(tmp_path: Path) -> None:
    """Pipeline should store only one edge for duplicate child URLs after normalization."""
    pipeline, repository = build_pipeline(tmp_path)
    blog = seed_blog(repository)

    pipeline.fetcher = FakeFetcher(
        {
            "https://blog.example.com/": FetchResult(
                url="https://blog.example.com/",
                status_code=200,
                text="<html><body><footer><a href='/friends'>友情链接</a></footer></body></html>",
            ),
            "https://blog.example.com/friends": FetchResult(
                url="https://blog.example.com/friends",
                status_code=200,
                text="""
                <html><body><section><h2>友情链接</h2>
                <a href='https://friend.example/'>Friend</a>
                <a href='https://friend.example/?utm_source=feed'>Friend Feed</a>
                </section></body></html>
                """,
            ),
        }
    )

    discovered = pipeline._crawl_blog(blog)

    assert discovered == 1
    edges = repository.list_edges()
    assert len(edges) == 1
    assert edges[0]["link_url_raw"] == "https://friend.example/"


def test_pipeline_skips_candidate_page_with_more_than_50_links(tmp_path: Path) -> None:
    """Overlarge candidate pages should not create raw URL records or edges."""
    pipeline, repository = build_pipeline(tmp_path)
    blog = seed_blog(repository)
    noisy_links = "\n".join(
        f"<a href='https://friend-{index}.example/'>Friend {index}</a>"
        for index in range(51)
    )

    pipeline.fetcher = FakeFetcher(
        {
            "https://blog.example.com/": FetchResult(
                url="https://blog.example.com/",
                status_code=200,
                text="""
                <html><body>
                <footer>
                  <a href="/friends">友情链接</a>
                  <a href="/friends-small">友情链接 Small</a>
                </footer>
                </body></html>
                """,
            ),
            "https://blog.example.com/friends": FetchResult(
                url="https://blog.example.com/friends",
                status_code=200,
                text=f"<html><body><section><h2>友情链接</h2>{noisy_links}</section></body></html>",
            ),
            "https://blog.example.com/friends-small": FetchResult(
                url="https://blog.example.com/friends-small",
                status_code=200,
                text="""
                <html><body><section><h2>友情链接</h2>
                <a href='https://small-friend.example/'>Small Friend</a>
                </section></body></html>
                """,
            ),
        }
    )

    discovered = pipeline._crawl_blog(blog)

    assert discovered == 1
    edges = repository.list_edges()
    assert len(edges) == 1
    assert edges[0]["link_url_raw"] == "https://small-friend.example/"
    with session_scope(repository.session_factory) as session:
        raw_urls = session.query(RawDiscoveredUrlModel).order_by(RawDiscoveredUrlModel.id).all()
        assert [row.normalized_url for row in raw_urls] == ["https://small-friend.example/"]


def test_pipeline_fetches_candidate_pages_concurrently_but_persists_in_candidate_order(
    tmp_path: Path,
) -> None:
    """Batch fetching may complete out of order, but persistence follows candidate order."""
    pipeline, repository = build_pipeline(tmp_path)
    blog = seed_blog(repository)

    homepage_html = """
    <html><body>
      <a href="/friends-a">友情链接 A</a>
      <a href="/friends-b">友情链接 B</a>
    </body></html>
    """
    first_page_html = """
    <html><body><section><h2>友情链接</h2>
      <a href="https://friend.example/">Earlier Candidate</a>
    </section></body></html>
    """
    second_page_html = """
    <html><body><section><h2>友情链接</h2>
      <a href="https://friend.example/?utm_source=later">Later Candidate</a>
    </section></body></html>
    """

    pipeline.fetcher = FakeFetcher(
        {
            "https://blog.example.com/": FetchResult(
                url="https://blog.example.com/",
                status_code=200,
                text=homepage_html,
            ),
        },
        batch_results={
            "https://blog.example.com/friends-b": FetchAttempt(
                request_url="https://blog.example.com/friends-b",
                result=FetchResult(
                    url="https://blog.example.com/friends-b",
                    status_code=200,
                    text=second_page_html,
                ),
                error_kind=None,
            ),
            "https://blog.example.com/friends-a": FetchAttempt(
                request_url="https://blog.example.com/friends-a",
                result=FetchResult(
                    url="https://blog.example.com/friends-a",
                    status_code=200,
                    text=first_page_html,
                ),
                error_kind=None,
            ),
        },
    )

    discovered = pipeline._crawl_blog(blog)

    assert discovered == 1
    assert len(pipeline.fetcher.fetch_many_calls) == 1
    fetched_urls, concurrency, timeout_seconds = pipeline.fetcher.fetch_many_calls[0]
    assert fetched_urls == [
        "https://blog.example.com/friends-a",
        "https://blog.example.com/friends-b",
    ]
    assert concurrency == 4
    assert timeout_seconds is not None
    assert timeout_seconds <= 60.0
    assert pipeline.fetcher.batch_completion_order == [
        "https://blog.example.com/friends-b",
        "https://blog.example.com/friends-a",
    ]
    edges = repository.list_edges()
    assert len(edges) == 1
    assert edges[0]["link_url_raw"] == "https://friend.example/"


def test_pipeline_skips_failed_candidate_page_without_aborting_remaining_pages(tmp_path: Path) -> None:
    """One failed candidate page should not block other successfully fetched pages."""
    pipeline, repository = build_pipeline(tmp_path)
    blog = seed_blog(repository)

    homepage_html = """
    <html><body>
      <a href="/friends-a">友情链接 A</a>
      <a href="/friends-b">友情链接 B</a>
    </body></html>
    """
    first_page_html = """
    <html><body><section><h2>友情链接</h2>
      <a href="https://friend.example/">Friend</a>
    </section></body></html>
    """

    pipeline.fetcher = FakeFetcher(
        {
            "https://blog.example.com/": FetchResult(
                url="https://blog.example.com/",
                status_code=200,
                text=homepage_html,
            ),
        },
        batch_results={
            "https://blog.example.com/friends-a": FetchAttempt(
                request_url="https://blog.example.com/friends-a",
                result=FetchResult(
                    url="https://blog.example.com/friends-a",
                    status_code=200,
                    text=first_page_html,
                ),
                error_kind=None,
            ),
            "https://blog.example.com/friends-b": FetchAttempt(
                request_url="https://blog.example.com/friends-b",
                result=None,
                error_kind="timeout",
            ),
        },
    )

    discovered = pipeline._crawl_blog(blog)

    assert discovered == 1
    edges = repository.list_edges()
    assert len(edges) == 1
    assert edges[0]["link_url_raw"] == "https://friend.example/"


def test_pipeline_marks_blog_failed_when_candidate_page_is_too_large(tmp_path: Path) -> None:
    """Oversized candidate pages should fail the source blog instead of being silently skipped."""
    pipeline, repository = build_pipeline(tmp_path)
    blog = seed_blog(repository)

    pipeline.fetcher = FakeFetcher(
        {
            "https://blog.example.com/": FetchResult(
                url="https://blog.example.com/",
                status_code=200,
                text="<html><body><a href='/friends'>友情链接</a></body></html>",
            ),
        },
        batch_results={
            "https://blog.example.com/friends": FetchAttempt(
                request_url="https://blog.example.com/friends",
                result=None,
                error_kind="page_too_large",
            )
        },
    )

    result = pipeline.process_blog_row(blog)

    assert result == {"processed": 1, "discovered": 0, "failed": 1}
    refreshed = repository.get_blog(int(blog["id"]))
    assert refreshed is not None
    assert refreshed["crawl_status"] == "FAILED"
    assert refreshed["status_code"] == 413


def test_pipeline_candidate_page_concurrency_of_one_matches_legacy_behavior(tmp_path: Path) -> None:
    """Concurrency 1 should preserve the existing crawl result semantics."""
    pipeline, repository = build_pipeline(tmp_path)
    pipeline.settings.candidate_page_fetch_concurrency = 1
    blog = seed_blog(repository)

    homepage_html = """
    <html><body>
      <footer><a href="/friends">友情链接</a></footer>
    </body></html>
    """
    friend_page_html = """
    <html><body><section><h2>友情链接</h2>
      <a href="https://friend.example/">Friend</a>
    </section></body></html>
    """
    pipeline.fetcher = FakeFetcher(
        {
            "https://blog.example.com/": FetchResult(
                url="https://blog.example.com/",
                status_code=200,
                text=homepage_html,
            ),
            "https://blog.example.com/friends": FetchResult(
                url="https://blog.example.com/friends",
                status_code=200,
                text=friend_page_html,
            ),
        }
    )

    discovered = pipeline._crawl_blog(blog)

    assert discovered == 1
    assert len(pipeline.fetcher.fetch_many_calls) == 1
    fetched_urls, concurrency, timeout_seconds = pipeline.fetcher.fetch_many_calls[0]
    assert fetched_urls == ["https://blog.example.com/friends"]
    assert concurrency == 1
    assert timeout_seconds is not None
    assert timeout_seconds <= 60.0
    assert repository.list_edges()[0]["link_url_raw"] == "https://friend.example/"


def test_pipeline_marks_blog_failed_when_total_crawl_time_budget_is_exhausted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single blog crawl should fail once its total time budget is exhausted."""
    pipeline, repository = build_pipeline(tmp_path)
    pipeline.settings.blog_crawl_timeout_seconds = 60.0
    blog = seed_blog(repository)

    clock = {"now": 1_000.0}

    def fake_monotonic() -> float:
        return clock["now"]

    monkeypatch.setattr("crawler.crawling.orchestrator.monotonic", fake_monotonic)

    pipeline.fetcher = FakeFetcher(
        {
            "https://blog.example.com/": FetchResult(
                url="https://blog.example.com/",
                status_code=200,
                text="<html><body><a href='/friends'>友情链接</a></body></html>",
            ),
        },
        batch_results={
            "https://blog.example.com/friends": FetchAttempt(
                request_url="https://blog.example.com/friends",
                result=FetchResult(
                    url="https://blog.example.com/friends",
                    status_code=200,
                    text="""
                    <html><body><section><h2>友情链接</h2>
                      <a href="https://friend.example/">Friend</a>
                    </section></body></html>
                    """,
                ),
                error_kind=None,
            ),
        },
        on_fetch=lambda _url, _timeout: clock.__setitem__("now", clock["now"] + 20.0),
        on_fetch_many=lambda _urls, _timeout: clock.__setitem__("now", clock["now"] + 45.0),
    )

    result = pipeline.process_blog_row(blog)

    refreshed = repository.get_blog(int(blog["id"]))
    assert result == {"processed": 1, "discovered": 0, "failed": 1}
    assert refreshed is not None
    assert refreshed["crawl_status"] == "FAILED"
    assert refreshed["friend_links_count"] == 0
    assert pipeline.fetcher.fetch_timeouts == [60.0]
    assert pipeline.fetcher.fetch_many_calls == [
        (["https://blog.example.com/friends"], 4, 40.0)
    ]
