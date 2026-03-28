"""Tests for the split-service entrypoints."""

from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import BackendState
from backend.main import create_app as create_backend_app
from frontend.server import create_app as create_frontend_app
from persistence_api.main import build_persistence_state
from persistence_api.main import create_app as create_persistence_app
from search.main import SearchService
from search.main import create_app as create_search_app
from shared.config import Settings


class StubCrawler:
    def bootstrap(self) -> dict[str, int]:
        return {"imported": 2}

    def run(self, max_nodes: int | None = None) -> dict[str, int | None]:
        return {"processed": max_nodes or 1, "discovered": 1, "failed": 0}

    def runtime_status(self) -> dict[str, object]:
        return {
            "runner_status": "idle",
            "active_run_id": None,
            "current_blog_id": None,
            "current_url": None,
            "current_stage": None,
            "last_started_at": None,
            "last_stopped_at": None,
            "last_error": None,
            "last_result": None,
        }

    def current(self) -> dict[str, object]:
        return self.runtime_status()

    def start(self) -> dict[str, object]:
        payload = self.runtime_status()
        payload["runner_status"] = "running"
        return payload

    def stop(self) -> dict[str, object]:
        return self.runtime_status()

    def run_batch(self, max_nodes: int) -> dict[str, object]:
        return {"accepted": True, "mode": "batch", "result": {"processed": max_nodes}}


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

    health = client.get("/internal/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    status = client.get("/api/status")
    assert status.status_code == 200
    assert status.json()["total_blogs"] == 3

    crawl = client.post("/api/crawl/run?max_nodes=2")
    assert crawl.status_code == 200
    assert crawl.json()["processed"] == 2
    assert search.reindexed is True

    runtime = client.get("/api/runtime/status")
    assert runtime.status_code == 200
    assert runtime.json()["runner_status"] == "idle"

    batch = client.post("/api/runtime/run-batch", json={"max_nodes": 3})
    assert batch.status_code == 200
    assert batch.json()["accepted"] is True


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


def test_frontend_service_health_checks_backend(tmp_path: Path, monkeypatch) -> None:
    """Frontend health should fail fast when its backend is unavailable."""

    class OkResponse:
        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, timeout: float) -> OkResponse:
        assert url == "http://backend:8000/api/status"
        assert timeout == 10.0
        return OkResponse()

    monkeypatch.setattr("frontend.server.httpx.get", fake_get)
    settings = Settings(
        db_path=tmp_path / "heyblog.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        backend_base_url="http://backend:8000",
    )
    app = create_frontend_app(settings)
    client = TestClient(app)

    health = client.get("/internal/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"


def test_frontend_service_serves_built_app_when_dist_exists(tmp_path: Path, monkeypatch) -> None:
    """Frontend routes should serve the built SPA instead of the fallback page."""
    dist_dir = tmp_path / "dist"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text("<!DOCTYPE html><title>Built App</title>", encoding="utf-8")

    monkeypatch.setattr("frontend.server.FRONTEND_DIST_DIR", dist_dir)
    monkeypatch.setattr("frontend.server.FRONTEND_ASSETS_DIR", assets_dir)

    settings = Settings(
        db_path=tmp_path / "heyblog.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        backend_base_url="http://backend:8000",
    )
    app = create_frontend_app(settings)
    client = TestClient(app)

    response = client.get("/stats")

    assert response.status_code == 200
    assert "Built App" in response.text
    assert "Frontend build is not ready" not in response.text
