"""Integration-style tests for the crawl pipeline discovery flow."""

from pathlib import Path

from app.config import Settings
from app.crawler.classifier import ClassifierUnavailableError
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


class RejectingClassifier:
    """Classifier test double that rejects every ambiguous link."""

    def review_links(self, page_url: str, page_html: str, links):  # type: ignore[no-untyped-def]
        raise ClassifierUnavailableError("classifier offline")


def build_pipeline(tmp_path: Path) -> tuple[CrawlPipeline, Repository]:
    """Construct a pipeline backed by a temporary repository."""
    settings = Settings(
        db_path=tmp_path / "db.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        max_outgoing_links_per_blog=10,
        max_candidate_pages_per_blog=3,
        max_path_probes_per_blog=2,
        friend_link_section_score_threshold=2.5,
        enable_mcp_classifier=False,
    )
    repository = Repository(settings.db_path)
    pipeline = CrawlPipeline(settings, repository)
    return pipeline, repository


def test_pipeline_persists_only_valid_friend_links(monkeypatch, tmp_path: Path) -> None:
    """Only validated friend links from scored sections should become edges."""
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

    monkeypatch.setattr("app.crawler.pipeline.build_classifier", lambda settings: None)

    discovered = pipeline._crawl_blog(blog)

    assert discovered == 1
    edges = repository.list_edges()
    assert len(edges) == 1
    assert edges[0]["link_url_raw"] == "https://friend.example/"


def test_pipeline_continues_when_classifier_is_unavailable(monkeypatch, tmp_path: Path) -> None:
    """Classifier outages should degrade safely to deterministic behavior."""
    pipeline, repository = build_pipeline(tmp_path)
    pipeline.settings.enable_mcp_classifier = True
    pipeline.settings.friend_link_ambiguity_threshold = 10.0

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
        <nav><a href="/friends">友情链接</a></nav>
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
            <li><a href="https://friend-two.example/">Friend Two</a></li>
            <li><a href="https://friend-three.example/">Friend Three</a></li>
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

    monkeypatch.setattr(
        "app.crawler.pipeline.build_classifier",
        lambda settings: RejectingClassifier(),
    )

    discovered = pipeline._crawl_blog(blog)

    assert discovered == 3
    logs = repository.list_logs()
    assert any(log["stage"] == "classifier" and log["result"] == "fallback" for log in logs)
