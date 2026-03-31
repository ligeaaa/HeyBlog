"""Integration-style tests for the crawl pipeline discovery flow."""

from pathlib import Path
from typing import Any

from crawler.fetcher import FetchAttempt
from crawler.fetcher import FetchResult
from crawler.pipeline import CrawlPipeline
from persistence_api.repository import Repository
from shared.config import Settings


class FakeFetcher:
    """Return pre-baked fetch responses for pipeline tests."""

    def __init__(
        self,
        responses: dict[str, FetchResult],
        *,
        batch_results: dict[str, FetchAttempt] | None = None,
    ) -> None:
        self.responses = responses
        self.batch_results = batch_results or {}
        self.calls: list[str] = []
        self.fetch_many_calls: list[tuple[list[str], int]] = []
        self.batch_completion_order: list[str] = []

    def fetch(self, url: str) -> FetchResult:
        self.calls.append(url)
        return self.responses[url]

    def fetch_many(self, urls: list[str], *, max_concurrency: int) -> dict[str, FetchAttempt]:
        self.fetch_many_calls.append((list(urls), max_concurrency))
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


def build_pipeline(tmp_path: Path) -> tuple[CrawlPipeline, Repository]:
    """Construct a pipeline backed by a temporary repository."""
    settings = Settings(
        db_path=tmp_path / "db.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        max_path_probes_per_blog=2,
        candidate_page_fetch_concurrency=4,
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
        depth=0,
        source_blog_id=None,
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
        }
    )

    discovered = pipeline._crawl_blog(blog)

    assert discovered == 1
    edges = repository.list_edges()
    assert len(edges) == 1
    assert edges[0]["link_url_raw"] == "https://friend.example/"


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
        }
    )

    pipeline._crawl_blog(blog)

    refreshed = repository.get_blog(int(blog["id"]))
    assert refreshed is not None
    assert refreshed["title"] == "Alpha Blog"
    assert refreshed["icon_url"] == "https://blog.example.com/static/favicon.png"


def test_pipeline_falls_back_to_origin_favicon_when_page_has_no_icon_link(tmp_path: Path) -> None:
    """Missing explicit icon markup should still produce an origin favicon candidate."""
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
    assert refreshed["icon_url"] == "https://blog.example.com/favicon.ico"


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
    assert pipeline.fetcher.fetch_many_calls == [
        (
            [
                "https://blog.example.com/friends-a",
                "https://blog.example.com/friends-b",
            ],
            4,
        )
    ]
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
    assert pipeline.fetcher.fetch_many_calls == [(["https://blog.example.com/friends"], 1)]
    assert repository.list_edges()[0]["link_url_raw"] == "https://friend.example/"
