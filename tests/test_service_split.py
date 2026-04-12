"""Tests for the split-service entrypoints."""

from pathlib import Path
from time import sleep

import httpx
from fastapi.testclient import TestClient

from backend.main import BackendState
from backend.main import create_app as create_backend_app
from frontend.server import create_app as create_frontend_app
from persistence_api.main import build_persistence_state
from persistence_api.main import create_app as create_persistence_app
from search.main import SearchService
from search.main import create_app as create_search_app
from shared.config import PROJECT_ROOT
from shared.config import Settings
from shared.http_clients.persistence_http import PersistenceHttpClient


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




def admin_headers(token: str = "secret-token") -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


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

    queue_catalog = client.get(
        "/internal/blogs/catalog",
        params={"statuses": "WAITING,PROCESSING", "sort": "id_asc"},
    )
    assert queue_catalog.status_code == 200
    assert queue_catalog.json()["filters"]["statuses"] == ["WAITING", "PROCESSING"]
    assert queue_catalog.json()["sort"] == "id_asc"

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

    priority_requests = client.get("/internal/ingestion-requests")
    assert priority_requests.status_code == 200
    assert priority_requests.json()[0]["request_id"] == 1
    assert "email" not in priority_requests.json()[0]
    assert "request_token" not in priority_requests.json()[0]
    assert "email" not in priority_requests.json()[0]["blog"]

    lookup = client.get("/internal/blogs/lookup", params={"url": "https://queued.example.com/"})
    assert lookup.status_code == 200
    assert lookup.json()["match_reason"] == "identity_key"
    assert lookup.json()["items"][0]["id"] == request.json()["seed_blog_id"]

    reset = client.post("/internal/database/reset")
    assert reset.status_code == 200
    assert reset.json()["blogs_deleted"] == 3
    assert reset.json()["logs_deleted"] == 0
    assert reset.json()["ingestion_requests_deleted"] == 1
    assert reset.json()["blog_link_labels_deleted"] == 0

    blogs = client.get("/internal/blogs")
    assert blogs.status_code == 200
    assert blogs.json() == []


def test_persistence_service_exposes_blog_labeling_endpoints(tmp_path: Path) -> None:
    """Persistence service should expose multi-tag candidate listing and label management."""
    settings = Settings(
        db_path=tmp_path / "heyblog.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
    )
    app = create_persistence_app(build_persistence_state(settings))
    client = TestClient(app)

    finished = client.post(
        "/internal/blogs/upsert",
        json={
            "url": "https://alpha.example/",
            "normalized_url": "https://alpha.example/",
            "domain": "alpha.example",
        },
    )
    waiting = client.post(
        "/internal/blogs/upsert",
        json={
            "url": "https://beta.example/",
            "normalized_url": "https://beta.example/",
            "domain": "beta.example",
        },
    )
    assert finished.status_code == 200
    assert waiting.status_code == 200

    mark_finished = client.post(
        f"/internal/blogs/{finished.json()['id']}/result",
        json={
            "crawl_status": "FINISHED",
            "status_code": 200,
            "friend_links_count": 1,
            "metadata_captured": True,
            "title": "Alpha",
            "icon_url": "https://alpha.example/favicon.ico",
        },
    )
    assert mark_finished.status_code == 200

    candidates = client.get("/internal/blog-labeling/candidates", params={"labeled": "false"})
    assert candidates.status_code == 200
    assert [row["id"] for row in candidates.json()["items"]] == [finished.json()["id"]]
    assert candidates.json()["items"][0]["labels"] == []
    assert candidates.json()["filters"]["labeled"] is False

    create_blog = client.post("/internal/blog-labeling/tags", json={"name": "blog"})
    create_official = client.post("/internal/blog-labeling/tags", json={"name": "official"})
    assert create_blog.status_code == 200
    assert create_official.status_code == 200

    tags = client.get("/internal/blog-labeling/tags")
    assert tags.status_code == 200
    assert [row["slug"] for row in tags.json()] == ["blog", "official"]

    put_label = client.put(
        f"/internal/blog-labeling/labels/{finished.json()['id']}",
        json={"tag_ids": [create_blog.json()["id"], create_official.json()["id"]]},
    )
    assert put_label.status_code == 200
    assert put_label.json()["label_slugs"] == ["blog", "official"]

    export_csv = client.get("/internal/blog-labeling/export")
    assert export_csv.status_code == 200
    assert export_csv.headers["content-type"].startswith("text/csv")
    assert export_csv.text.splitlines() == [
        "url,title,label",
        "https://alpha.example/,Alpha,blog",
        "https://alpha.example/,Alpha,official",
    ]

    labeled = client.get(
        "/internal/blog-labeling/candidates",
        params={"label": "official", "labeled": "true", "sort": "recently_labeled"},
    )
    assert labeled.status_code == 200
    assert [row["id"] for row in labeled.json()["items"]] == [finished.json()["id"]]
    assert labeled.json()["items"][0]["is_labeled"] is True
    assert [row["slug"] for row in labeled.json()["items"][0]["labels"]] == ["blog", "official"]

    invalid_label = client.post("/internal/blog-labeling/tags", json={"name": "   "})
    assert invalid_label.status_code == 422

    conflict = client.put(
        f"/internal/blog-labeling/labels/{waiting.json()['id']}",
        json={"tag_ids": [create_blog.json()["id"]]},
    )
    assert conflict.status_code == 409

    missing = client.put("/internal/blog-labeling/labels/999", json={"tag_ids": [create_blog.json()["id"]]})
    assert missing.status_code == 404

    unknown_tag = client.put(
        f"/internal/blog-labeling/labels/{finished.json()['id']}",
        json={"tag_ids": [999]},
    )
    assert unknown_tag.status_code == 422


def test_persistence_http_client_uses_put_for_blog_labeling_updates() -> None:
    """The split-service HTTP client must preserve the persistence route method."""

    class StubResponse:
        def __init__(self) -> None:
            self.called = False

        def raise_for_status(self) -> None:
            self.called = True

        def json(self) -> dict[str, object]:
            return {"ok": True}

    class StubClient:
        def __init__(self) -> None:
            self.put_calls: list[tuple[str, dict[str, object]]] = []
            self.post_calls: list[tuple[str, dict[str, object]]] = []

        def put(self, path: str, json: dict[str, object]) -> StubResponse:
            self.put_calls.append((path, json))
            return StubResponse()

        def post(self, path: str, json: dict[str, object]) -> StubResponse:
            self.post_calls.append((path, json))
            return StubResponse()

    client = PersistenceHttpClient("http://persistence.internal")
    stub = StubClient()
    client.client = stub  # type: ignore[assignment]

    response = client.replace_blog_link_labels(blog_id=7, tag_ids=[3, 5])

    assert response == {"ok": True}
    assert stub.put_calls == [("/internal/blog-labeling/labels/7", {"tag_ids": [3, 5]})]
    assert stub.post_calls == []


def test_persistence_http_client_can_fetch_blog_label_training_csv() -> None:
    """The split-service HTTP client should support plain-text CSV exports."""

    class StubResponse:
        text = "url,title,label\nhttps://alpha.example/,Alpha,blog\n"

        def raise_for_status(self) -> None:
            return None

    class StubClient:
        def __init__(self) -> None:
            self.get_calls: list[tuple[str, dict[str, object] | None]] = []

        def get(self, path: str, params: dict[str, object] | None = None) -> StubResponse:
            self.get_calls.append((path, params))
            return StubResponse()

    client = PersistenceHttpClient("http://persistence.internal")
    stub = StubClient()
    client.client = stub  # type: ignore[assignment]

    response = client.export_blog_label_training_csv()

    assert response == "url,title,label\nhttps://alpha.example/,Alpha,blog\n"
    assert stub.get_calls == [("/internal/blog-labeling/export", None)]


def test_settings_can_enable_postgres_runtime(tmp_path: Path, monkeypatch) -> None:
    """Environment loading should allow the split runtime to point at Postgres."""
    monkeypatch.setenv("HEYBLOG_DB_DSN", "postgresql://heyblog:heyblog@persistence-db:5432/heyblog")
    monkeypatch.setenv("HEYBLOG_DB_PATH", str(tmp_path / "unused.sqlite"))
    monkeypatch.setenv("HEYBLOG_SEED_PATH", str(tmp_path / "seed.csv"))
    monkeypatch.setenv("HEYBLOG_EXPORT_DIR", str(tmp_path / "exports"))

    settings = Settings.from_env()

    assert settings.db_dsn == "postgresql://heyblog:heyblog@persistence-db:5432/heyblog"


def test_settings_default_runtime_model_root_uses_runtime_resources(monkeypatch) -> None:
    """Environment loading should default runtime model reads to published resources."""
    monkeypatch.delenv("HEYBLOG_DECISION_MODEL_ROOT", raising=False)

    settings = Settings.from_env()

    assert settings.decision_model_root == PROJECT_ROOT / "runtime_resources" / "models" / "url_decision" / "current"


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
                        "statuses": kwargs.get("statuses"),
                        "sort": kwargs.get("sort", "id_desc"),
                        "has_title": kwargs.get("has_title"),
                        "has_icon": kwargs.get("has_icon"),
                        "min_connections": kwargs.get("min_connections", 0),
                    },
                "sort": kwargs.get("sort", "id_desc"),
            },
            "list_blog_labeling_candidates": lambda self, **kwargs: {
                "items": [
                    {
                        "id": 3,
                        "url": "https://catalog.example.com",
                        "normalized_url": "https://catalog.example.com",
                        "domain": "catalog.example.com",
                        "email": None,
                        "title": "Catalog Example",
                        "icon_url": "https://catalog.example.com/favicon.ico",
                        "status_code": 200,
                        "crawl_status": "FINISHED",
                        "friend_links_count": 2,
                        "last_crawled_at": "2026-03-31T00:00:00Z",
                        "created_at": "2026-03-31T00:00:00Z",
                        "updated_at": "2026-03-31T00:00:00Z",
                        "incoming_count": 1,
                        "outgoing_count": 2,
                        "connection_count": 3,
                        "activity_at": "2026-03-31T00:00:00Z",
                        "identity_complete": True,
                        "labels": (
                            [
                                {
                                    "id": 11,
                                    "name": "official",
                                    "slug": "official",
                                    "created_at": "2026-04-05T00:00:00Z",
                                    "updated_at": "2026-04-05T00:00:00Z",
                                    "labeled_at": "2026-04-05T00:00:00Z",
                                }
                            ]
                            if kwargs.get("label")
                            else []
                        ),
                        "label_slugs": [kwargs.get("label")] if kwargs.get("label") else [],
                        "last_labeled_at": "2026-04-05T00:00:00Z" if kwargs.get("label") else None,
                        "is_labeled": kwargs.get("label") is not None,
                    }
                ],
                "available_tags": [
                    {
                        "id": 10,
                        "name": "blog",
                        "slug": "blog",
                        "created_at": "2026-04-05T00:00:00Z",
                        "updated_at": "2026-04-05T00:00:00Z",
                    },
                    {
                        "id": 11,
                        "name": "official",
                        "slug": "official",
                        "created_at": "2026-04-05T00:00:00Z",
                        "updated_at": "2026-04-05T00:00:00Z",
                    },
                ],
                "page": kwargs.get("page", 1),
                "page_size": kwargs.get("page_size", 50),
                "total_items": 1,
                "total_pages": 1,
                "has_next": False,
                "has_prev": False,
                "filters": {
                    "q": kwargs.get("q"),
                    "label": kwargs.get("label"),
                    "labeled": kwargs.get("labeled"),
                    "sort": kwargs.get("sort", "id_desc"),
                },
                "sort": kwargs.get("sort", "id_desc"),
            },
            "list_blog_label_tags": lambda self: [
                {
                    "id": 10,
                    "name": "blog",
                    "slug": "blog",
                    "created_at": "2026-04-05T00:00:00Z",
                    "updated_at": "2026-04-05T00:00:00Z",
                }
            ],
            "export_blog_label_training_csv": lambda self: (
                "url,title,label\n"
                "https://catalog.example.com,Catalog Example,official\n"
            ),
            "create_blog_label_tag": lambda self, name: {
                "id": 12,
                "name": name,
                "slug": name.lower(),
                "created_at": "2026-04-05T00:00:00Z",
                "updated_at": "2026-04-05T00:00:00Z",
            },
            "replace_blog_link_labels": lambda self, blog_id, tag_ids: {
                "blog_id": blog_id,
                "labels": [
                    {
                        "id": tag_id,
                        "name": f"tag-{tag_id}",
                        "slug": f"tag-{tag_id}",
                        "created_at": "2026-04-05T00:00:00Z",
                        "updated_at": "2026-04-05T00:00:00Z",
                        "labeled_at": "2026-04-05T00:00:00Z",
                    }
                    for tag_id in tag_ids
                ],
                "label_slugs": [f"tag-{tag_id}" for tag_id in tag_ids],
                "last_labeled_at": "2026-04-05T00:00:00Z" if tag_ids else None,
                "is_labeled": bool(tag_ids),
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
            "list_priority_ingestion_requests": lambda self: [
                {
                    "request_id": 9,
                    "requested_url": "https://queued.example/",
                    "normalized_url": "https://queued.example/",
                    "status": "QUEUED",
                    "seed_blog_id": 3,
                    "matched_blog_id": None,
                    "blog_id": 3,
                    "error_message": None,
                    "created_at": "2026-04-05T00:00:00Z",
                    "updated_at": "2026-04-05T00:00:00Z",
                    "blog": {
                        "id": 3,
                        "url": "https://queued.example/",
                        "normalized_url": "https://queued.example/",
                        "domain": "queued.example",
                        "title": "Queued Example",
                        "icon_url": None,
                        "status_code": None,
                        "crawl_status": "WAITING",
                        "friend_links_count": 0,
                        "last_crawled_at": None,
                        "created_at": "2026-04-05T00:00:00Z",
                        "updated_at": "2026-04-05T00:00:00Z",
                        "incoming_count": 0,
                        "outgoing_count": 0,
                        "connection_count": 0,
                        "activity_at": None,
                        "identity_complete": True,
                    },
                }
            ],
            "lookup_blog_candidates": lambda self, url: {
                "query_url": url,
                "normalized_query_url": "https://queued.example/",
                "items": [
                    {
                        "id": 3,
                        "url": "https://queued.example/",
                        "normalized_url": "https://queued.example/",
                        "domain": "queued.example",
                        "email": None,
                        "title": "Queued Example",
                        "icon_url": None,
                        "status_code": None,
                        "crawl_status": "WAITING",
                        "friend_links_count": 0,
                        "last_crawled_at": None,
                        "created_at": "2026-04-05T00:00:00Z",
                        "updated_at": "2026-04-05T00:00:00Z",
                        "incoming_count": 0,
                        "outgoing_count": 0,
                        "connection_count": 0,
                        "activity_at": None,
                        "identity_complete": True,
                    }
                ],
                "total_matches": 1,
                "match_reason": "identity_key",
            },
            "reset": lambda self: {
                "ok": True,
                "blogs_deleted": 3,
                "edges_deleted": 4,
                "logs_deleted": 0,
                "ingestion_requests_deleted": 1,
                "blog_link_labels_deleted": 1,
                "blog_label_tags_deleted": 2,
            },
        },
    )()
    search = StubSearch()
    app = create_backend_app(BackendState(persistence=persistence, crawler=StubCrawler(), search=search, admin_token="secret-token"))
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

    queue_catalog = client.get("/api/blogs/catalog?statuses=WAITING,PROCESSING&sort=id_asc")
    assert queue_catalog.status_code == 200
    assert queue_catalog.json()["filters"]["statuses"] == "WAITING,PROCESSING"
    assert queue_catalog.json()["sort"] == "id_asc"

    labeling = client.get("/api/admin/blog-labeling/candidates?page=2&page_size=25&label=official&labeled=true", headers=admin_headers())
    assert labeling.status_code == 200
    assert labeling.json()["page"] == 2
    assert labeling.json()["filters"]["label"] == "official"
    assert labeling.json()["filters"]["labeled"] == "true"
    assert labeling.json()["available_tags"][0]["slug"] == "blog"

    labeling_export = client.get("/api/admin/blog-labeling/export", headers=admin_headers())
    assert labeling_export.status_code == 200
    assert labeling_export.headers["content-type"].startswith("text/csv")
    assert labeling_export.text == "url,title,label\nhttps://catalog.example.com,Catalog Example,official\n"

    tag_create = client.post("/api/admin/blog-labeling/tags", json={"name": "government"}, headers=admin_headers())
    assert tag_create.status_code == 200
    assert tag_create.json()["slug"] == "government"

    label_update = client.put("/api/admin/blog-labeling/labels/3", json={"tag_ids": [10, 11]}, headers=admin_headers())
    assert label_update.status_code == 200
    assert label_update.json()["blog_id"] == 3
    assert label_update.json()["label_slugs"] == ["tag-10", "tag-11"]

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

    crawl = client.post("/api/admin/crawl/run?max_nodes=2", headers=admin_headers())
    assert crawl.status_code == 200
    assert crawl.json()["processed"] == 2
    assert search.reindexed is True

    runtime = client.get("/api/admin/runtime/status", headers=admin_headers())
    assert runtime.status_code == 200
    assert runtime.json()["runner_status"] == "idle"
    assert runtime.json()["worker_count"] == 3
    assert runtime.json()["workers"] == []

    batch = client.post("/api/admin/runtime/run-batch", json={"max_nodes": 3}, headers=admin_headers())
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

    priority_ingestion = client.get("/api/ingestion-requests")
    assert priority_ingestion.status_code == 200
    assert priority_ingestion.json()[0]["request_id"] == 9
    assert "email" not in priority_ingestion.json()[0]
    assert "request_token" not in priority_ingestion.json()[0]
    assert "email" not in priority_ingestion.json()[0]["blog"]

    lookup = client.get("/api/blogs/lookup?url=https://queued.example/")
    assert lookup.status_code == 200
    assert lookup.json()["match_reason"] == "identity_key"
    assert lookup.json()["items"][0]["id"] == 3

    reset = client.post("/api/admin/database/reset", headers=admin_headers())
    assert reset.status_code == 200
    assert reset.json()["blogs_deleted"] == 3
    assert reset.json()["ingestion_requests_deleted"] == 1
    assert reset.json()["blog_link_labels_deleted"] == 1
    assert reset.json()["blog_label_tags_deleted"] == 2
    assert reset.json()["search_reindexed"] is True
    assert search.reindex_calls == 3


def test_backend_blog_labeling_surfaces_upstream_errors() -> None:
    """Public labeling endpoints should preserve upstream validation and conflict errors."""

    class LabelingValidationStub:
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
            return {"items": [], "page": 1, "page_size": 50, "total_items": 0, "total_pages": 0, "has_next": False, "has_prev": False, "filters": {}, "sort": "id_desc"}

        def list_blog_labeling_candidates(self, **_: object) -> dict[str, object]:
            request = httpx.Request("GET", "http://persistence/internal/blog-labeling/candidates")
            response = httpx.Response(422, request=request, json={"detail": "Unsupported blog label name"})
            raise httpx.HTTPStatusError("boom", request=request, response=response)

        def list_blog_label_tags(self) -> list[dict[str, object]]:
            return []

        def create_blog_label_tag(self, *, name: str) -> dict[str, object]:
            request = httpx.Request("POST", "http://persistence/internal/blog-labeling/tags")
            response = httpx.Response(422, request=request, json={"detail": "Unsupported blog label name"})
            raise httpx.HTTPStatusError("boom", request=request, response=response)

        def replace_blog_link_labels(self, *, blog_id: int, tag_ids: list[int]) -> dict[str, object]:
            request = httpx.Request("PUT", f"http://persistence/internal/blog-labeling/labels/{blog_id}")
            response = httpx.Response(
                409,
                request=request,
                json={"detail": "blog_labeling_requires_finished_blog"},
            )
            raise httpx.HTTPStatusError("boom", request=request, response=response)

        def export_blog_label_training_csv(self) -> str:
            request = httpx.Request("GET", "http://persistence/internal/blog-labeling/export")
            response = httpx.Response(422, request=request, json={"detail": "Unsupported blog label name"})
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
        BackendState(persistence=LabelingValidationStub(), crawler=StubCrawler(), search=StubSearch(), admin_token="secret-token")
    )
    client = TestClient(app)

    list_response = client.get("/api/admin/blog-labeling/candidates?label=maybe", headers=admin_headers())
    assert list_response.status_code == 422
    assert list_response.json()["detail"] == "Unsupported blog label name"

    post_response = client.post("/api/admin/blog-labeling/tags", json={"name": "   "}, headers=admin_headers())
    assert post_response.status_code == 422
    assert post_response.json()["detail"] == "Unsupported blog label name"

    put_response = client.put("/api/admin/blog-labeling/labels/1", json={"tag_ids": [7]}, headers=admin_headers())
    assert put_response.status_code == 409
    assert put_response.json()["detail"] == "blog_labeling_requires_finished_blog"

    export_response = client.get("/api/admin/blog-labeling/export", headers=admin_headers())
    assert export_response.status_code == 422
    assert export_response.json()["detail"] == "Unsupported blog label name"


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

    response = client.get("/api/blogs/catalog?statuses=WAITING,BAD")
    assert response.status_code == 422
    assert response.json()["detail"] == "Unsupported crawl status: BAD"


def test_backend_lookup_and_priority_list_surface_upstream_validation_errors() -> None:
    """Public lookup and priority list endpoints should preserve upstream failures."""

    class LookupValidationStub:
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
            return {"items": [], "page": 1, "page_size": 50, "total_items": 0, "total_pages": 0, "has_next": False, "has_prev": False, "filters": {}, "sort": "id_desc"}

        def lookup_blog_candidates(self, *, url: str) -> dict[str, object]:
            request = httpx.Request("GET", "http://persistence/internal/blogs/lookup")
            response = httpx.Response(422, request=request, json={"detail": "Unsupported homepage URL"})
            raise httpx.HTTPStatusError("boom", request=request, response=response)

        def list_priority_ingestion_requests(self) -> list[dict[str, object]]:
            request = httpx.Request("GET", "http://persistence/internal/ingestion-requests")
            response = httpx.Response(503, request=request, json={"detail": "upstream_unavailable"})
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
        BackendState(persistence=LookupValidationStub(), crawler=StubCrawler(), search=StubSearch())
    )
    client = TestClient(app)

    lookup = client.get("/api/blogs/lookup?url=notaurl")
    assert lookup.status_code == 422
    assert lookup.json()["detail"] == "Unsupported homepage URL"

    priority = client.get("/api/ingestion-requests")
    assert priority.status_code == 503
    assert priority.json()["detail"] == "upstream_unavailable"


def test_backend_graph_neighbors_surfaces_upstream_not_found() -> None:
    """Public graph neighborhood endpoint should preserve upstream 404 errors."""

    class GraphNeighborNotFoundStub:
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
            request = httpx.Request("GET", f"http://persistence/internal/graph/nodes/{blog_id}/neighbors")
            response = httpx.Response(404, request=request, json={"detail": "graph_node_not_found"})
            raise httpx.HTTPStatusError("boom", request=request, response=response)

        def latest_graph_snapshot(self) -> dict[str, object]:
            return {"version": "v1"}

        def graph_snapshot(self, version: str) -> dict[str, object]:
            return {"version": version, "nodes": [], "edges": [], "meta": {}}

        def list_logs(self) -> list[dict[str, object]]:
            return []

        def reset(self) -> dict[str, object]:
            return {"ok": True, "blogs_deleted": 0, "edges_deleted": 0, "logs_deleted": 0}

    app = create_backend_app(
        BackendState(persistence=GraphNeighborNotFoundStub(), crawler=StubCrawler(), search=StubSearch())
    )
    client = TestClient(app)

    response = client.get("/api/graph/nodes/99/neighbors?hops=1&limit=40")
    assert response.status_code == 404
    assert response.json()["detail"] == "graph_node_not_found"


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
        BackendState(
            persistence=persistence,
            crawler=BusyCrawler(),
            search=StubSearch(),
            admin_token="secret-token",
        )
    )
    client = TestClient(app)

    reset = client.post("/api/admin/database/reset", headers=admin_headers())

    assert reset.status_code == 409
    assert reset.json()["detail"] == "crawler_busy"


def test_backend_admin_routes_require_valid_token() -> None:
    app = create_backend_app(
        BackendState(
            persistence=type("PersistenceStub", (), {"stats": lambda self: {}})(),
            crawler=StubCrawler(),
            search=StubSearch(),
            admin_token="secret-token",
        )
    )
    client = TestClient(app)

    missing = client.get("/api/admin/runtime/status")
    assert missing.status_code == 401
    assert missing.json()["detail"] == "admin_auth_required"

    invalid = client.get("/api/admin/runtime/status", headers=admin_headers("wrong-token"))
    assert invalid.status_code == 403
    assert invalid.json()["detail"] == "admin_auth_invalid"


def test_backend_admin_routes_fail_when_auth_not_configured() -> None:
    app = create_backend_app(
        BackendState(
            persistence=type("PersistenceStub", (), {"stats": lambda self: {}})(),
            crawler=StubCrawler(),
            search=StubSearch(),
        )
    )
    client = TestClient(app)

    response = client.get("/api/admin/runtime/status", headers=admin_headers())

    assert response.status_code == 503
    assert response.json()["detail"] == "admin_auth_not_configured"


def test_persistence_service_exposes_blog_dedup_scan_endpoints(tmp_path: Path) -> None:
    """Persistence should expose decision-rescan summary and removed item endpoints."""
    settings = Settings(
        db_path=tmp_path / "heyblog.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
    )
    app = create_persistence_app(build_persistence_state(settings))
    client = TestClient(app)

    first = client.post(
        "/internal/blogs/upsert",
        json={
            "url": "https://langhai.cc/",
            "normalized_url": "https://langhai.cc/",
            "domain": "langhai.cc",
        },
    )
    assert first.status_code == 200

    run = client.post("/internal/blog-dedup-scans", params={"crawler_was_running": "true"})
    assert run.status_code == 200
    assert run.json()["status"] == "SUCCEEDED"
    assert run.json()["total_count"] == 1

    latest = client.get("/internal/blog-dedup-scans/latest")
    assert latest.status_code == 200
    assert latest.json()["id"] == run.json()["id"]

    by_id = client.get(f"/internal/blog-dedup-scans/{run.json()['id']}")
    assert by_id.status_code == 200
    assert by_id.json()["ruleset_version"] == run.json()["ruleset_version"]

    items = client.get(f"/internal/blog-dedup-scans/{run.json()['id']}/items")
    assert items.status_code == 200
    assert isinstance(items.json(), list)


def test_backend_blog_dedup_scan_stops_and_restarts_crawler_and_blocks_runtime_actions() -> None:
    """Admin scan should orchestrate stop/scan/restart and expose maintenance lock."""

    class ScanPersistenceStub:
        def __init__(self) -> None:
            self.finalize_calls: list[dict[str, object]] = []
            self.run = {
                "id": 7,
                "status": "PENDING",
                "ruleset_version": "2026-04-07-v2",
                "total_count": 3,
                "scanned_count": 0,
                "removed_count": 0,
                "kept_count": 0,
                "crawler_was_running": True,
                "crawler_restart_attempted": False,
                "crawler_restart_succeeded": False,
                "search_reindexed": False,
                "error_message": None,
            }

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

        def create_blog_dedup_scan_run(self, *, crawler_was_running: bool = False) -> dict[str, object]:
            self.run.update(
                {
                    "status": "RUNNING",
                    "crawler_was_running": crawler_was_running,
                    "crawler_restart_attempted": False,
                    "crawler_restart_succeeded": False,
                    "search_reindexed": False,
                    "error_message": None,
                }
            )
            return dict(self.run)

        def execute_blog_dedup_scan_run(self, *, run_id: int) -> dict[str, object]:
            sleep(0.05)
            self.run.update(
                {
                    "id": run_id,
                    "status": "SUCCEEDED",
                    "scanned_count": 3,
                    "removed_count": 2,
                    "kept_count": 1,
                }
            )
            return dict(self.run)

        def run_blog_dedup_scan(self, *, crawler_was_running: bool = False) -> dict[str, object]:
            self.create_blog_dedup_scan_run(crawler_was_running=crawler_was_running)
            return self.execute_blog_dedup_scan_run(run_id=7)

        def finalize_blog_dedup_scan_run(self, **payload: object) -> dict[str, object]:
            self.finalize_calls.append(payload)
            self.run.update(
                {
                    "id": int(payload["run_id"]),
                    "crawler_restart_attempted": bool(payload["crawler_restart_attempted"]),
                    "crawler_restart_succeeded": bool(payload["crawler_restart_succeeded"]),
                    "search_reindexed": bool(payload["search_reindexed"]),
                    "error_message": payload.get("error_message"),
                }
            )
            return dict(self.run)

        def latest_blog_dedup_scan_run(self) -> dict[str, object]:
            return dict(self.run)

        def get_blog_dedup_scan_run(self, run_id: int) -> dict[str, object]:
            return self.latest_blog_dedup_scan_run() | {"id": run_id}

        def list_blog_dedup_scan_run_items(self, run_id: int) -> list[dict[str, object]]:
            return [
                {
                    "id": 1,
                    "run_id": run_id,
                    "removed_url": "http://blog.langhai.cc/index.html",
                    "reason_code": "blog_alias_collapsed",
                    "survivor_selection_basis": "FINISHED, created_at=2026-04-05T00:00:00Z, id=1",
                }
            ]

    class ToggleCrawler(StubCrawler):
        def __init__(self) -> None:
            self.runner_status = "running"
            self.stop_calls = 0
            self.start_calls = 0

        def runtime_status(self) -> dict[str, object]:
            payload = super().runtime_status()
            payload["runner_status"] = self.runner_status
            return payload

        def stop(self) -> dict[str, object]:
            self.stop_calls += 1
            self.runner_status = "idle"
            return self.runtime_status()

        def start(self) -> dict[str, object]:
            self.start_calls += 1
            self.runner_status = "running"
            return self.runtime_status()

    persistence = ScanPersistenceStub()
    crawler = ToggleCrawler()
    search = StubSearch()
    app = create_backend_app(BackendState(persistence=persistence, crawler=crawler, search=search, admin_token="secret-token"))
    client = TestClient(app)

    response = client.post("/api/admin/blog-dedup-scans", headers=admin_headers())

    assert response.status_code == 200
    assert response.json()["status"] == "RUNNING"
    assert response.json()["total_count"] == 3
    assert crawler.stop_calls == 1
    for _ in range(20):
        latest = client.get("/api/admin/blog-dedup-scans/latest", headers=admin_headers())
        assert latest.status_code == 200
        if latest.json()["status"] == "SUCCEEDED":
            break
        sleep(0.05)
    assert latest.json()["crawler_restart_attempted"] is True
    assert latest.json()["crawler_restart_succeeded"] is True
    assert latest.json()["search_reindexed"] is True
    assert crawler.start_calls == 1
    items = client.get("/api/admin/blog-dedup-scans/7/items", headers=admin_headers())
    assert items.status_code == 200
    assert items.json()[0]["reason_code"] == "blog_alias_collapsed"


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


def test_frontend_root_serves_spa_entry(tmp_path: Path) -> None:
    """Frontend root should serve the SPA entry instead of redirecting."""
    settings = Settings(
        db_path=tmp_path / "heyblog.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        backend_base_url="http://backend:8000",
    )
    app = create_frontend_app(settings)
    client = TestClient(app)

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 200
    assert '<div id="root"></div>' in response.text


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


def test_frontend_service_proxies_put_api_requests(tmp_path: Path, monkeypatch) -> None:
    """Frontend API proxy should forward PUT requests to the backend service."""

    captured: dict[str, object] = {}

    class StubAsyncResponse:
        def __init__(self) -> None:
            self.content = b'{"ok":true}'
            self.status_code = 200
            self.headers = {"content-type": "application/json"}

    class StubAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self) -> "StubAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def request(
            self,
            method: str,
            url: str,
            *,
            params: object,
            content: bytes,
            headers: dict[str, str],
        ) -> StubAsyncResponse:
            captured["method"] = method
            captured["url"] = url
            captured["params"] = dict(params)
            captured["content"] = content
            captured["headers"] = headers
            return StubAsyncResponse()

    monkeypatch.setattr("frontend.server.httpx.AsyncClient", StubAsyncClient)
    settings = Settings(
        db_path=tmp_path / "heyblog.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        backend_base_url="http://backend:8000",
    )
    app = create_frontend_app(settings)
    client = TestClient(app)

    response = client.put("/api/admin/blog-labeling/labels/1", json={"tag_ids": [10, 11]}, headers=admin_headers())

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert captured == {
        "timeout": 60.0,
        "method": "PUT",
        "url": "http://backend:8000/api/admin/blog-labeling/labels/1",
        "params": {},
        "content": b'{"tag_ids":[10,11]}',
        "headers": {
            "content-type": "application/json",
            "authorization": "Bearer secret-token",
        },
    }
