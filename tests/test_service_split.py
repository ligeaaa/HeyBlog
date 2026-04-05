"""Tests for the split-service entrypoints."""

from pathlib import Path

import httpx
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
            "worker_count": 3,
            "active_workers": 0,
            "current_worker_id": None,
            "current_blog_id": None,
            "current_url": None,
            "current_stage": None,
            "task_started_at": None,
            "elapsed_seconds": None,
            "last_started_at": None,
            "last_stopped_at": None,
            "last_error": None,
            "last_result": None,
            "workers": [],
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
        self.reindex_calls = 0

    def search(self, query: str, kind: str = "all", limit: int = 10) -> dict[str, object]:
        return {
            "query": query,
            "kind": kind,
            "limit": limit,
            "blogs": [{"domain": "blog.example.com"}],
            "edges": [],
            "logs": [],
        }

    def reindex(self) -> dict[str, bool]:
        self.reindexed = True
        self.reindex_calls += 1
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
        },
    )
    assert created.status_code == 200
    assert created.json()["inserted"] is True

    related = client.post(
        "/internal/blogs/upsert",
        json={
            "url": "https://friend.example.com/",
            "normalized_url": "https://friend.example.com/",
            "domain": "friend.example.com",
        },
    )
    assert related.status_code == 200
    assert related.json()["inserted"] is True

    blogs = client.get("/internal/blogs")
    assert blogs.status_code == 200
    assert blogs.json()[0]["domain"] == "blog.example.com"

    catalog = client.get(
        "/internal/blogs/catalog",
        params={"page": 0, "page_size": 500, "status": " finished "},
    )
    assert catalog.status_code == 200
    assert catalog.json()["page"] == 1
    assert catalog.json()["page_size"] == 200
    assert catalog.json()["filters"]["status"] == "FINISHED"

    invalid_catalog = client.get("/internal/blogs/catalog?status=invalid")
    assert invalid_catalog.status_code == 422

    empty_optional_filters = client.get(
        "/internal/blogs/catalog",
        params={"has_title": "", "has_icon": "", "min_connections": ""},
    )
    assert empty_optional_filters.status_code == 200
    assert empty_optional_filters.json()["filters"]["has_title"] is None
    assert empty_optional_filters.json()["filters"]["has_icon"] is None
    assert empty_optional_filters.json()["filters"]["min_connections"] == 0

    updated = client.post(
        "/internal/blogs/1/result",
        json={
            "crawl_status": "FINISHED",
            "status_code": 200,
            "friend_links_count": 3,
            "metadata_captured": True,
            "title": "Blog Example",
            "icon_url": "https://blog.example.com/favicon.ico",
        },
    )
    assert updated.status_code == 200

    related_updated = client.post(
        "/internal/blogs/2/result",
        json={
            "crawl_status": "FINISHED",
            "status_code": 200,
            "friend_links_count": 1,
            "metadata_captured": True,
            "title": "Friend Example",
            "icon_url": "https://friend.example.com/favicon.ico",
        },
    )
    assert related_updated.status_code == 200

    edge = client.post(
        "/internal/edges",
        json={
            "from_blog_id": 2,
            "to_blog_id": 1,
            "link_url_raw": "https://blog.example.com/",
            "link_text": "Main blog",
        },
    )
    assert edge.status_code == 200

    blog = client.get("/internal/blogs/1")
    assert blog.status_code == 200
    assert blog.json()["title"] == "Blog Example"
    assert blog.json()["icon_url"] == "https://blog.example.com/favicon.ico"

    detail = client.get("/internal/blogs/1/detail")
    assert detail.status_code == 200
    assert detail.json()["incoming_edges"][0]["neighbor_blog"] == {
        "id": 2,
        "domain": "friend.example.com",
        "title": "Friend Example",
        "icon_url": "https://friend.example.com/favicon.ico",
    }
    assert detail.json()["outgoing_edges"] == []

    request = client.post(
        "/internal/ingestion-requests",
        json={
            "homepage_url": "https://queued.example.com/",
            "email": "owner@example.com",
        },
    )
    assert request.status_code == 200
    assert request.json()["request_id"] == 1
    assert request.json()["status"] == "QUEUED"

    request_status = client.get(
        "/internal/ingestion-requests/1",
        params={"request_token": request.json()["request_token"]},
    )
    assert request_status.status_code == 200
    assert request_status.json()["email"] == "owner@example.com"

    reset = client.post("/internal/database/reset")
    assert reset.status_code == 200
    assert reset.json()["blogs_deleted"] == 3
    assert reset.json()["logs_deleted"] == 0
    assert reset.json()["ingestion_requests_deleted"] == 1

    blogs = client.get("/internal/blogs")
    assert blogs.status_code == 200
    assert blogs.json() == []


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
                "average_friend_links": 1.0,
            },
            "list_blogs": lambda self: [
                {
                    "id": 1,
                    "domain": "blog.example.com",
                    "email": None,
                    "title": "Blog Example",
                    "icon_url": "https://blog.example.com/favicon.ico",
                }
            ],
            "list_blogs_catalog": lambda self, **kwargs: {
                "items": [
                    {
                        "id": 3,
                        "domain": "catalog.example.com",
                        "email": None,
                        "title": "Catalog Example",
                        "icon_url": "https://catalog.example.com/favicon.ico",
                        "incoming_count": 1,
                        "outgoing_count": 2,
                        "connection_count": 3,
                        "activity_at": "2026-03-31T00:00:00Z",
                        "identity_complete": True,
                    }
                ],
                "page": kwargs.get("page", 1),
                "page_size": kwargs.get("page_size", 50),
                "total_items": 1,
                "total_pages": 1,
                "has_next": False,
                "has_prev": False,
                "filters": {
                    "q": kwargs.get("q"),
                    "site": kwargs.get("site"),
                    "url": kwargs.get("url"),
                    "status": kwargs.get("status"),
                    "sort": kwargs.get("sort", "id_desc"),
                    "has_title": kwargs.get("has_title"),
                    "has_icon": kwargs.get("has_icon"),
                    "min_connections": kwargs.get("min_connections", 0),
                },
                "sort": kwargs.get("sort", "id_desc"),
            },
            "get_blog": lambda self, blog_id: {
                "id": blog_id,
                "domain": "blog.example.com",
                "email": None,
                "title": "Blog Example",
                "icon_url": "https://blog.example.com/favicon.ico",
            },
            "get_blog_detail": lambda self, blog_id: {
                "id": blog_id,
                "domain": "blog.example.com",
                "email": None,
                "title": "Blog Example",
                "icon_url": "https://blog.example.com/favicon.ico",
                "incoming_count": 1,
                "outgoing_count": 1,
                "connection_count": 2,
                "activity_at": "2026-03-31T00:00:00Z",
                "identity_complete": True,
                "incoming_edges": [
                    {
                        "id": 10,
                        "from_blog_id": 2,
                        "to_blog_id": blog_id,
                        "link_url_raw": "https://blog.example.com",
                        "link_text": "Blog Example",
                        "discovered_at": "2026-03-31T00:00:00Z",
                        "neighbor_blog": {
                            "id": 2,
                            "domain": "friend.example.com",
                            "title": "Friend Example",
                            "icon_url": "https://friend.example.com/favicon.ico",
                        },
                    }
                ],
                "outgoing_edges": [
                    {
                        "id": 11,
                        "from_blog_id": blog_id,
                        "to_blog_id": 3,
                        "link_url_raw": "https://catalog.example.com",
                        "link_text": "Catalog Example",
                        "discovered_at": "2026-03-31T00:00:00Z",
                        "neighbor_blog": {
                            "id": 3,
                            "domain": "catalog.example.com",
                            "title": "Catalog Example",
                            "icon_url": "https://catalog.example.com/favicon.ico",
                        },
                    }
                ],
                "recommended_blogs": [
                    {
                        "blog": {
                            "id": 4,
                            "domain": "delta.example.com",
                            "email": None,
                            "title": "Delta Example",
                            "icon_url": "https://delta.example.com/favicon.ico",
                            "url": "https://delta.example.com",
                            "normalized_url": "https://delta.example.com",
                            "status_code": 200,
                            "crawl_status": "FINISHED",
                            "friend_links_count": 2,
                            "last_crawled_at": "2026-03-31T00:00:00Z",
                            "created_at": "2026-03-31T00:00:00Z",
                            "updated_at": "2026-03-31T00:00:00Z",
                            "incoming_count": 1,
                            "outgoing_count": 0,
                            "connection_count": 1,
                            "activity_at": "2026-03-31T00:00:00Z",
                            "identity_complete": True,
                        },
                        "reason": "mutual_connection",
                        "mutual_connection_count": 1,
                        "via_blogs": [
                            {
                                "id": 3,
                                "domain": "catalog.example.com",
                                "title": "Catalog Example",
                                "icon_url": "https://catalog.example.com/favicon.ico",
                            }
                        ],
                    }
                ],
            },
            "list_edges": lambda self: [],
            "graph": lambda self: {"nodes": [], "edges": []},
            "graph_view": lambda self, **kwargs: {
                "nodes": [],
                "edges": [],
                "meta": {
                    "strategy": kwargs.get("strategy", "degree"),
                    "limit": kwargs.get("limit", 180),
                    "sample_mode": kwargs.get("sample_mode", "off"),
                    "sample_value": kwargs.get("sample_value"),
                    "sample_seed": kwargs.get("sample_seed", 7),
                    "sampled": False,
                    "focus_node_id": None,
                    "hops": None,
                    "has_stable_positions": True,
                    "snapshot_version": "v1",
                    "generated_at": "2026-03-31T00:00:00Z",
                    "source": "snapshot",
                    "total_nodes": 3,
                    "total_edges": 4,
                    "available_nodes": 3,
                    "available_edges": 4,
                    "selected_nodes": 0,
                    "selected_edges": 0,
                },
            },
            "graph_neighbors": lambda self, blog_id, hops=1, limit=120: {
                "nodes": [
                    {
                        "id": blog_id,
                        "domain": "blog.example.com",
                        "title": "Blog Example",
                        "icon_url": "https://blog.example.com/favicon.ico",
                    }
                ],
                "edges": [],
                "meta": {
                    "strategy": "neighborhood",
                    "limit": limit,
                    "sample_mode": "off",
                    "sample_value": None,
                    "sample_seed": 0,
                    "sampled": False,
                    "focus_node_id": blog_id,
                    "hops": hops,
                    "has_stable_positions": True,
                    "snapshot_version": "v1",
                    "generated_at": "2026-03-31T00:00:00Z",
                    "source": "snapshot",
                    "total_nodes": 3,
                    "total_edges": 4,
                    "available_nodes": 3,
                    "available_edges": 4,
                    "selected_nodes": 1,
                    "selected_edges": 0,
                },
            },
            "latest_graph_snapshot": lambda self: {
                "version": "v1",
                "generated_at": "2026-03-31T00:00:00Z",
                "source": "snapshot",
                "has_stable_positions": True,
                "total_nodes": 3,
                "total_edges": 4,
                "available_nodes": 3,
                "available_edges": 4,
                "file": "graph-layout-v1.json",
            },
            "graph_snapshot": lambda self, version: {
                "version": version,
                "generated_at": "2026-03-31T00:00:00Z",
                "nodes": [],
                "edges": [],
                "meta": {
                    "strategy": "degree",
                    "limit": 180,
                    "sample_mode": "off",
                    "sample_value": None,
                    "sample_seed": 7,
                    "sampled": False,
                    "focus_node_id": None,
                    "hops": None,
                    "has_stable_positions": True,
                    "snapshot_version": version,
                    "generated_at": "2026-03-31T00:00:00Z",
                    "source": "snapshot",
                    "total_nodes": 3,
                    "total_edges": 4,
                    "available_nodes": 3,
                    "available_edges": 4,
                    "selected_nodes": 0,
                    "selected_edges": 0,
                },
            },
            "list_logs": lambda self: [],
            "create_ingestion_request": lambda self, homepage_url, email: {
                "id": 9,
                "request_id": 9,
                "requested_url": homepage_url,
                "normalized_url": homepage_url,
                "email": email,
                "status": "QUEUED",
                "priority": 100,
                "seed_blog_id": 3,
                "matched_blog_id": None,
                "blog_id": 3,
                "request_token": "token-123",
                "expires_at": None,
                "error_message": None,
                "created_at": "2026-04-05T00:00:00Z",
                "updated_at": "2026-04-05T00:00:00Z",
                "seed_blog": None,
                "matched_blog": None,
                "blog": None,
            },
            "get_ingestion_request": lambda self, request_id, request_token: {
                "id": request_id,
                "request_id": request_id,
                "requested_url": "https://queued.example/",
                "normalized_url": "https://queued.example/",
                "email": "owner@example.com",
                "status": "QUEUED",
                "priority": 100,
                "seed_blog_id": 3,
                "matched_blog_id": None,
                "blog_id": 3,
                "request_token": request_token,
                "expires_at": None,
                "error_message": None,
                "created_at": "2026-04-05T00:00:00Z",
                "updated_at": "2026-04-05T00:00:00Z",
                "seed_blog": None,
                "matched_blog": None,
                "blog": None,
            },
            "reset": lambda self: {
                "ok": True,
                "blogs_deleted": 3,
                "edges_deleted": 4,
                "logs_deleted": 0,
                "ingestion_requests_deleted": 1,
            },
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

    blogs = client.get("/api/blogs")
    assert blogs.status_code == 200
    assert blogs.json()[0]["title"] == "Blog Example"
    assert blogs.json()[0]["icon_url"] == "https://blog.example.com/favicon.ico"

    detail = client.get("/api/blogs/1")
    assert detail.status_code == 200
    assert detail.json()["incoming_edges"][0]["neighbor_blog"]["domain"] == "friend.example.com"
    assert detail.json()["outgoing_edges"][0]["neighbor_blog"]["domain"] == "catalog.example.com"

    catalog = client.get("/api/blogs/catalog?page=2&page_size=25&site=blog&status=FINISHED&sort=connections")
    assert catalog.status_code == 200
    assert catalog.json()["page"] == 2
    assert catalog.json()["page_size"] == 25
    assert catalog.json()["filters"]["site"] == "blog"
    assert catalog.json()["filters"]["status"] == "FINISHED"
    assert catalog.json()["sort"] == "connections"

    core_view = client.get("/api/graph/views/core?strategy=degree&limit=80")
    assert core_view.status_code == 200
    assert core_view.json()["meta"]["limit"] == 80

    neighbors = client.get("/api/graph/nodes/1/neighbors?hops=2&limit=40")
    assert neighbors.status_code == 200
    assert neighbors.json()["meta"]["focus_node_id"] == 1
    assert neighbors.json()["nodes"][0]["title"] == "Blog Example"

    latest_snapshot = client.get("/api/graph/snapshots/latest")
    assert latest_snapshot.status_code == 200
    assert latest_snapshot.json()["version"] == "v1"

    crawl = client.post("/api/crawl/run?max_nodes=2")
    assert crawl.status_code == 200
    assert crawl.json()["processed"] == 2
    assert search.reindexed is True

    runtime = client.get("/api/runtime/status")
    assert runtime.status_code == 200
    assert runtime.json()["runner_status"] == "idle"
    assert runtime.json()["worker_count"] == 3
    assert runtime.json()["workers"] == []

    batch = client.post("/api/runtime/run-batch", json={"max_nodes": 3})
    assert batch.status_code == 200
    assert batch.json()["accepted"] is True

    ingestion = client.post(
        "/api/ingestion-requests",
        json={"homepage_url": "https://queued.example/", "email": "owner@example.com"},
    )
    assert ingestion.status_code == 200
    assert ingestion.json()["request_id"] == 9

    ingestion_status = client.get("/api/ingestion-requests/9?request_token=token-123")
    assert ingestion_status.status_code == 200
    assert ingestion_status.json()["status"] == "QUEUED"

    reset = client.post("/api/database/reset")
    assert reset.status_code == 200
    assert reset.json()["blogs_deleted"] == 3
    assert reset.json()["ingestion_requests_deleted"] == 1
    assert reset.json()["search_reindexed"] is True
    assert search.reindex_calls == 3


def test_backend_blog_catalog_surfaces_upstream_validation_errors() -> None:
    """Public catalog endpoint should preserve upstream 422 validation failures."""

    class CatalogValidationStub:
        def stats(self) -> dict[str, object]:
            return {
                "pending_tasks": 0,
                "processing_tasks": 0,
                "finished_tasks": 0,
                "failed_tasks": 0,
                "total_blogs": 0,
                "total_edges": 0,
                "status_counts": {},
                "average_friend_links": 0.0,
            }

        def list_blogs(self) -> list[dict[str, object]]:
            return []

        def list_blogs_catalog(self, **_: object) -> dict[str, object]:
            request = httpx.Request("GET", "http://persistence/internal/blogs/catalog")
            response = httpx.Response(422, request=request, json={"detail": "Unsupported crawl status: BAD"})
            raise httpx.HTTPStatusError("boom", request=request, response=response)

        def get_blog(self, blog_id: int) -> None:
            return None

        def get_blog_detail(self, blog_id: int) -> None:
            return None

        def list_edges(self) -> list[dict[str, object]]:
            return []

        def graph(self) -> dict[str, object]:
            return {"nodes": [], "edges": []}

        def graph_view(self, **_: object) -> dict[str, object]:
            return {"nodes": [], "edges": [], "meta": {}}

        def graph_neighbors(self, blog_id: int, hops: int = 1, limit: int = 120) -> dict[str, object]:
            return {"nodes": [], "edges": [], "meta": {}}

        def latest_graph_snapshot(self) -> dict[str, object]:
            return {"version": "v1"}

        def graph_snapshot(self, version: str) -> dict[str, object]:
            return {"version": version, "nodes": [], "edges": [], "meta": {}}

        def list_logs(self) -> list[dict[str, object]]:
            return []

        def reset(self) -> dict[str, object]:
            return {"ok": True, "blogs_deleted": 0, "edges_deleted": 0, "logs_deleted": 0}

    app = create_backend_app(
        BackendState(persistence=CatalogValidationStub(), crawler=StubCrawler(), search=StubSearch())
    )
    client = TestClient(app)

    response = client.get("/api/blogs/catalog?status=bad")
    assert response.status_code == 422
    assert response.json()["detail"] == "Unsupported crawl status: BAD"


def test_backend_database_reset_requires_idle_runtime() -> None:
    """Database reset should be rejected while the crawler runtime is busy."""

    class BusyCrawler(StubCrawler):
        def runtime_status(self) -> dict[str, object]:
            payload = super().runtime_status()
            payload["runner_status"] = "running"
            return payload

    persistence = type(
        "PersistenceStub",
        (),
        {
            "stats": lambda self: {
                "pending_tasks": 0,
                "processing_tasks": 0,
                "finished_tasks": 0,
                "failed_tasks": 0,
                "total_blogs": 0,
                "total_edges": 0,
                "status_counts": {},
                "average_friend_links": 0.0,
            },
            "list_blogs": lambda self: [],
            "get_blog": lambda self, blog_id: None,
            "list_edges": lambda self: [],
            "graph": lambda self: {"nodes": [], "edges": []},
            "graph_view": lambda self, **kwargs: {"nodes": [], "edges": [], "meta": {}},
            "graph_neighbors": lambda self, blog_id, hops=1, limit=120: {"nodes": [], "edges": [], "meta": {}},
            "latest_graph_snapshot": lambda self: {"version": "v1"},
            "graph_snapshot": lambda self, version: {"version": version, "nodes": [], "edges": [], "meta": {}},
            "list_logs": lambda self: [],
            "reset": lambda self: {
                "ok": True,
                "blogs_deleted": 0,
                "edges_deleted": 0,
                "logs_deleted": 0,
            },
        },
    )()
    app = create_backend_app(
        BackendState(persistence=persistence, crawler=BusyCrawler(), search=StubSearch())
    )
    client = TestClient(app)

    reset = client.post("/api/database/reset")

    assert reset.status_code == 409
    assert reset.json()["detail"] == "crawler_busy"


def test_search_service_queries_rebuilt_snapshot(tmp_path: Path) -> None:
    """Search service should return matches from its rebuildable snapshot."""

    class SnapshotStub:
        def search_snapshot(self) -> dict[str, list[dict[str, object]]]:
            return {
                "blogs": [{"domain": "blog.example.com", "url": "https://blog.example.com/"}],
                "edges": [{"link_text": "Friend Blog", "link_url_raw": "https://friend.example/"}],
                "logs": [],
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
    assert result.json()["logs"] == []


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


def test_frontend_root_redirects_to_stats(tmp_path: Path) -> None:
    """Frontend root should redirect browsers to the stats page."""
    settings = Settings(
        db_path=tmp_path / "heyblog.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        backend_base_url="http://backend:8000",
    )
    app = create_frontend_app(settings)
    client = TestClient(app)

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/stats"


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
