"""Integration-style tests for the crawl pipeline discovery flow."""

from pathlib import Path

from app.config import Settings
from app.crawler.fetcher import FetchResult
from app.crawler.pipeline import CrawlPipeline
from app.db.repository import Repository


class FakeFetcher:
    """Return pre-baked fetch responses for pipeline tests."""

    def __init__(self, responses: dict[str, FetchResult]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def fetch(self, url: str) -> FetchResult:
        self.calls.append(url)
        return self.responses[url]


def build_pipeline(tmp_path: Path) -> tuple[CrawlPipeline, Repository]:
    """Construct a pipeline backed by a temporary repository."""
    settings = Settings(
        db_path=tmp_path / "db.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        max_path_probes_per_blog=2,
    )
    repository = Repository(settings.db_path)
    pipeline = CrawlPipeline(settings, repository)
    return pipeline, repository


def test_pipeline_persists_only_valid_friend_links(tmp_path: Path) -> None:
    """Only validated friend links from extracted sections should become edges."""
    pipeline, repository = build_pipeline(tmp_path)
    blog_id, _ = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
        depth=0,
        source_blog_id=None,
    )
    blog = repository.get_blog(blog_id)
    assert blog is not None

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


def test_pipeline_uses_fallback_paths_when_homepage_has_no_friend_link_entry(tmp_path: Path) -> None:
    """Pipeline should still try fallback friend-link paths when homepage gives no signal."""
    pipeline, repository = build_pipeline(tmp_path)
    blog_id, _ = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
        depth=0,
        source_blog_id=None,
    )
    blog = repository.get_blog(blog_id)
    assert blog is not None

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

    blog_id, _ = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
        depth=0,
        source_blog_id=None,
    )
    blog = repository.get_blog(blog_id)
    assert blog is not None

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
