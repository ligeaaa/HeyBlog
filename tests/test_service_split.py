"""Tests for the split-service entrypoints."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from services.backend.main import BackendState
from services.backend.main import create_app as create_backend_app
from services.persistence.main import build_persistence_state
from services.persistence.main import create_app as create_persistence_app
from services.search.main import SearchService
from services.search.main import create_app as create_search_app


class StubCrawler:
    def bootstrap(self) -> dict[str, int]:
        return {"imported": 2}

    def run(self, max_nodes: int | None = None) -> dict[str, int | None]:
        return {"processed": max_nodes or 1, "discovered": 1, "failed": 0}


class StubSearch:
    def __init__(self) -> None:
        self.reindexed = False

    def search(self, query: str) -> dict[str, object]:
        return {"query": query, "blogs": [{"domain": "blog.example.com"}], "edges": [], "logs": []}

    def reindex(self) -> dict[str, bool]:
        self.reindexed = True
        return {"ok": True}


def test_persistence_service_exposes_repository_data(tmp_path: Path) -> None:
    """Persistence service should expose repository operations over HTTP."""
    settings = Settings(
        db_path=tmp_path / "heyblog.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
    )
    state = build_persistence_state(settings)
    app = create_persistence_app(state)
    client = TestClient(app)

    created = client.post(
        "/internal/blogs/upsert",
        json={
            "url": "https://blog.example.com/",
            "normalized_url": "https://blog.example.com/",
            "domain": "blog.example.com",
            "depth": 0,
            "source_blog_id": None,
        },
    )
    assert created.status_code == 200
    assert created.json()["inserted"] is True

    blogs = client.get("/internal/blogs")
    assert blogs.status_code == 200
    assert blogs.json()[0]["domain"] == "blog.example.com"


def test_settings_can_enable_postgres_runtime(tmp_path: Path, monkeypatch) -> None:
    """Environment loading should allow the split runtime to point at Postgres."""
    monkeypatch.setenv("HEYBLOG_DB_DSN", "postgresql://heyblog:heyblog@persistence-db:5432/heyblog")
    monkeypatch.setenv("HEYBLOG_DB_PATH", str(tmp_path / "unused.sqlite"))
    monkeypatch.setenv("HEYBLOG_SEED_PATH", str(tmp_path / "seed.csv"))
    monkeypatch.setenv("HEYBLOG_EXPORT_DIR", str(tmp_path / "exports"))

    settings = Settings.from_env()

    assert settings.db_dsn == "postgresql://heyblog:heyblog@persistence-db:5432/heyblog"


def test_backend_service_preserves_public_api_shape() -> None:
    """Backend service should serve the same public-facing API fields."""
    persistence = type(
        "PersistenceStub",
        (),
        {
            "stats": lambda self: {
                "pending_tasks": 1,
                "processing_tasks": 0,
                "finished_tasks": 2,
                "failed_tasks": 0,
                "total_blogs": 3,
                "total_edges": 4,
                "status_counts": {},
                "max_depth": 1,
                "average_friend_links": 1.0,
            },
            "list_blogs": lambda self: [{"id": 1, "domain": "blog.example.com"}],
            "get_blog": lambda self, blog_id: {"id": blog_id, "domain": "blog.example.com"},
            "list_edges": lambda self: [],
            "graph": lambda self: {"nodes": [], "edges": []},
            "list_logs": lambda self: [],
        },
    )()
    search = StubSearch()
    app = create_backend_app(BackendState(persistence=persistence, crawler=StubCrawler(), search=search))
    client = TestClient(app)

    status = client.get("/api/status")
    assert status.status_code == 200
    assert status.json()["total_blogs"] == 3

    crawl = client.post("/api/crawl/run?max_nodes=2")
    assert crawl.status_code == 200
    assert crawl.json()["processed"] == 2
    assert search.reindexed is True


def test_search_service_queries_rebuilt_snapshot(tmp_path: Path) -> None:
    """Search service should return matches from its rebuildable snapshot."""

    class SnapshotStub:
        def search_snapshot(self) -> dict[str, list[dict[str, object]]]:
            return {
                "blogs": [{"domain": "blog.example.com", "url": "https://blog.example.com/"}],
                "edges": [{"link_text": "Friend Blog", "link_url_raw": "https://friend.example/"}],
                "logs": [{"message": "Crawled blog.example.com"}],
            }

    service = SearchService(
        persistence=SnapshotStub(),
        cache_path=tmp_path / "search-cache" / "search-index.json",
    )
    app = create_search_app(service)
    client = TestClient(app)

    rebuild = client.post("/internal/search/reindex")
    assert rebuild.status_code == 200

    result = client.get("/internal/search?q=friend")
    assert result.status_code == 200
    assert result.json()["edges"][0]["link_text"] == "Friend Blog"
