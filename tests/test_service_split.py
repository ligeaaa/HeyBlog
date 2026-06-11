"""Tests for the split-service entrypoints."""

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import BackendState
from backend.main import create_app as create_backend_app
from persistence_api.email_delivery import EmailDeliveryError
from frontend.server import create_app as create_frontend_app
from persistence_api.main import PersistenceState
from persistence_api.main import build_persistence_state
from persistence_api.main import create_app as create_persistence_app
from search.main import SearchService
from search.main import create_app as create_search_app
from shared.config import PROJECT_ROOT
from shared.config import Settings
from shared.http_clients.persistence_http import PersistenceHttpClient


def _read_json_lines(path: Path) -> list[dict[str, object]]:
    """Read one JSON-lines log file."""

    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _single_log_file(path: Path) -> Path:
    """Return the only log file in a directory."""

    files = list(path.glob("*.log"))
    assert len(files) == 1
    return files[0]


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


def test_persistence_service_exposes_supported_repository_data(tmp_path: Path) -> None:
    """Persistence service should expose the supported repository-backed surfaces over HTTP."""
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

    requeue_result = client.post("/internal/blogs/requeue-failed")
    assert requeue_result.status_code == 200
    assert requeue_result.json() == {"requeued": 0}

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

    detail = client.get("/internal/blogs/1/detail")
    assert detail.status_code == 200
    assert detail.json()["incoming_edges"][0]["neighbor_blog"] == {
        "id": 2,
        "blog_id": 2,
        "domain": "friend.example.com",
        "title": "Friend Example",
        "icon_url": "https://friend.example.com/favicon.ico",
    }
    assert detail.json()["outgoing_edges"] == []

    auth = client.post(
        "/internal/users/register",
        json={"email": "Member@Example.com", "password": "long enough"},
    )
    assert auth.status_code == 200
    assert auth.json()["sent"] is True
    assert client.post(
        "/internal/users/login",
        json={"email": "member@example.com", "password": "long enough"},
    ).status_code == 401
    verified_auth = client.post(
        "/internal/users/email-verification/confirm",
        json={"token": auth.json()["verification_token"]},
    )
    assert verified_auth.status_code == 200
    assert verified_auth.json()["email"] == "member@example.com"
    login = client.post(
        "/internal/users/login",
        json={"email": "member@example.com", "password": "long enough"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["id"] == verified_auth.json()["id"]
    token = login.json()["token"]
    assert client.get("/internal/users/me", params={"session_token": token}).json()["id"] == verified_auth.json()["id"]

    lookup = client.get("/internal/blogs/lookup", params={"url": "https://blog.example.com/"})
    assert lookup.status_code == 200
    assert lookup.json()["match_reason"] == "identity_key"
    assert lookup.json()["items"][0]["id"] == 1

    filter_stats = client.get("/internal/filter-stats")
    assert filter_stats.status_code == 200
    assert filter_stats.json()["by_filter_reason"]["raw"] == 0

    reset = client.post("/internal/database/reset")
    assert reset.status_code == 200
    assert reset.json()["blogs_deleted"] == 2
    assert reset.json()["edges_deleted"] == 1
    assert reset.json()["raw_discovered_urls_deleted"] == 0
    assert reset.json()["logs_deleted"] == 0

    empty_catalog = client.get("/internal/blogs/catalog")
    assert empty_catalog.status_code == 200
    assert empty_catalog.json()["items"] == []


def test_persistence_user_registration_translates_email_delivery_failure(tmp_path: Path) -> None:
    """SMTP failures should return a stable API error instead of leaking provider details."""

    class FailingEmailDelivery:
        """Email sender that always fails during lifecycle delivery."""

        def send_verification_email(self, *, to_email: str, verification_url: str) -> None:
            """Raise a delivery error for one verification message.

            Args:
                to_email: Recipient email address.
                verification_url: One-time verification URL.

            Returns:
                None.
            """

            del to_email, verification_url
            raise EmailDeliveryError("email_delivery_failed")

        def send_password_reset_email(self, *, to_email: str, reset_url: str) -> None:
            """Raise a delivery error for one password reset message.

            Args:
                to_email: Recipient email address.
                reset_url: One-time password reset URL.

            Returns:
                None.
            """

            del to_email, reset_url
            raise EmailDeliveryError("email_delivery_failed")

    settings = Settings(
        db_path=tmp_path / "heyblog.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
    )
    state = build_persistence_state(settings)
    state.repository.email_delivery = FailingEmailDelivery()
    app = create_persistence_app(state)
    client = TestClient(app)

    response = client.post("/internal/users/register", json={"email": "user@example.com", "password": "long enough"})

    assert response.status_code == 502
    assert response.json()["detail"] == "email_delivery_failed"


def test_persistence_service_removes_legacy_read_shortcuts(tmp_path: Path) -> None:
    """Persistence service should not expose obsolete raw-read shortcut endpoints."""
    settings = Settings(
        db_path=tmp_path / "heyblog.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
    )
    app = create_persistence_app(build_persistence_state(settings))
    client = TestClient(app)

    assert client.get("/internal/blogs").status_code == 404
    assert client.get("/internal/blogs/1").status_code == 404
    assert client.get("/internal/edges").status_code == 405
    assert client.get("/internal/logs").status_code == 405
    assert client.get("/internal/graph").status_code == 404


def test_persistence_service_queue_routes_preserve_optional_row_serialization() -> None:
    """Queue routes should keep dict payloads and null semantics unchanged."""

    class StubRepository:
        def __init__(self) -> None:
            self.calls = 0

        def get_next_waiting_blog(self) -> dict[str, object] | None:
            self.calls += 1
            return {
                "id": 11,
                "blog_id": 11,
                "domain": "queued.example.com",
                "crawl_status": "PROCESSING",
            }

    repository = StubRepository()
    app = create_persistence_app(
        PersistenceState(
            repository=repository,  # type: ignore[arg-type]
            graph_service=object(),  # type: ignore[arg-type]
            stats_service=object(),  # type: ignore[arg-type]
        )
    )
    client = TestClient(app)

    waiting = client.get("/internal/queue/next")

    assert waiting.status_code == 200
    assert waiting.json() == {
        "id": 11,
        "blog_id": 11,
        "domain": "queued.example.com",
        "crawl_status": "PROCESSING",
    }
    assert repository.calls == 1


def test_persistence_service_zero_arg_list_routes_preserve_payload_passthrough() -> None:
    """Zero-arg list routes should keep list payloads and ordering unchanged."""

    class StubRepository:
        def list_blog_label_tags(self) -> list[dict[str, object]]:
            return [
                {"id": 7, "slug": "blog"},
                {"id": 8, "slug": "official"},
            ]

    app = create_persistence_app(
        PersistenceState(
            repository=StubRepository(),  # type: ignore[arg-type]
            graph_service=object(),  # type: ignore[arg-type]
            stats_service=object(),  # type: ignore[arg-type]
        )
    )
    client = TestClient(app)

    blog_label_tags = client.get("/internal/blog-labeling/tags")

    assert blog_label_tags.status_code == 200
    assert blog_label_tags.json() == [
        {"id": 7, "slug": "blog"},
        {"id": 8, "slug": "official"},
    ]


def test_persistence_service_zero_arg_dict_routes_preserve_payload_passthrough() -> None:
    """Zero-arg dict routes should keep dict payloads unchanged."""

    class StubGraphService:
        def graph_status(self) -> dict[str, object]:
            return {"backend": "snapshot", "enabled": True}

        def latest_snapshot_manifest(self) -> dict[str, object]:
            return {"version": "v7", "total_nodes": 42}

    app = create_persistence_app(
        PersistenceState(
            repository=object(),  # type: ignore[arg-type]
            graph_service=StubGraphService(),  # type: ignore[arg-type]
            stats_service=object(),  # type: ignore[arg-type]
        )
    )
    client = TestClient(app)

    graph_status = client.get("/internal/graph/status")
    latest_snapshot = client.get("/internal/graph/snapshots/latest")

    assert graph_status.status_code == 200
    assert graph_status.json() == {"backend": "snapshot", "enabled": True}

    assert latest_snapshot.status_code == 200
    assert latest_snapshot.json() == {"version": "v7", "total_nodes": 42}


def test_persistence_service_stats_routes_preserve_zero_arg_dict_passthrough() -> None:
    """Stats routes should keep zero-arg dict payloads unchanged."""

    class StubRepository:
        def get_filter_stats_by_chain_order(self) -> dict[str, object]:
            return {
                "by_filter_reason": {
                    "raw": 12,
                    "rule:same_domain": 9,
                }
            }

    class StubStatsService:
        def stats(self) -> dict[str, object]:
            return {
                "total_blogs": 17,
                "raw_discovered_urls": 12,
                "pending_tasks": 3,
            }

    app = create_persistence_app(
        PersistenceState(
            repository=StubRepository(),  # type: ignore[arg-type]
            graph_service=object(),  # type: ignore[arg-type]
            stats_service=StubStatsService(),  # type: ignore[arg-type]
        )
    )
    client = TestClient(app)

    stats = client.get("/internal/stats")
    filter_stats = client.get("/internal/filter-stats")

    assert stats.status_code == 200
    assert stats.json() == {
        "total_blogs": 17,
        "raw_discovered_urls": 12,
        "pending_tasks": 3,
    }

    assert filter_stats.status_code == 200
    assert filter_stats.json() == {
        "by_filter_reason": {
            "raw": 12,
            "rule:same_domain": 9,
        }
    }


def test_backend_icon_proxy_returns_valid_image(monkeypatch) -> None:
    """Backend icon proxy should return image bytes through the same origin."""
    app = create_backend_app(BackendState(persistence=object(), crawler=StubCrawler(), search=StubSearch()))
    client = TestClient(app)

    class FakeStreamResponse:
        status_code = 200
        headers = {"content-type": "image/png", "content-length": "8"}
        url = "https://icons.example.com/favicon.png"

        def __enter__(self) -> "FakeStreamResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self):
            yield b"png-bytes"

    def fake_stream(method: str, url: str, **kwargs: object) -> FakeStreamResponse:
        assert method == "GET"
        assert url == "https://icons.example.com/favicon.png"
        assert kwargs["follow_redirects"] is False
        assert kwargs["timeout"] == 8.0
        return FakeStreamResponse()

    monkeypatch.setattr("backend.main._is_private_icon_proxy_host", lambda hostname: False)
    monkeypatch.setattr("backend.main.httpx.stream", fake_stream)

    response = client.get("/api/icons/proxy", params={"url": "https://icons.example.com/favicon.png"})

    assert response.status_code == 200
    assert response.content == b"png-bytes"
    assert response.headers["content-type"].startswith("image/png")
    assert response.headers["cache-control"] == "public, max-age=86400"


def test_backend_icon_proxy_rejects_unsafe_urls() -> None:
    """Backend icon proxy should reject unsupported or private URL targets."""
    app = create_backend_app(BackendState(persistence=object(), crawler=StubCrawler(), search=StubSearch()))
    client = TestClient(app)

    unsupported = client.get("/api/icons/proxy", params={"url": "file:///etc/passwd"})
    loopback = client.get("/api/icons/proxy", params={"url": "http://127.0.0.1/favicon.ico"})

    assert unsupported.status_code == 422
    assert unsupported.json()["detail"] == "unsupported_icon_url"
    assert loopback.status_code == 422
    assert loopback.json()["detail"] == "unsafe_icon_url"


def test_backend_icon_proxy_rejects_private_redirects(monkeypatch) -> None:
    """Backend icon proxy should re-check redirect targets before fetching them."""
    app = create_backend_app(BackendState(persistence=object(), crawler=StubCrawler(), search=StubSearch()))
    client = TestClient(app)

    class RedirectResponse:
        status_code = 302
        headers = {"location": "http://127.0.0.1/favicon.ico"}
        url = "https://icons.example.com/favicon.png"

        def __enter__(self) -> "RedirectResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_stream(method: str, url: str, **kwargs: object) -> RedirectResponse:
        del method, url, kwargs
        return RedirectResponse()

    monkeypatch.setattr("backend.main._is_private_icon_proxy_host", lambda hostname: hostname == "127.0.0.1")
    monkeypatch.setattr("backend.main.httpx.stream", fake_stream)

    response = client.get("/api/icons/proxy", params={"url": "https://icons.example.com/favicon.png"})

    assert response.status_code == 422
    assert response.json()["detail"] == "unsafe_icon_url"


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
    accepted_raw = client.post(
        "/internal/raw-discovered-urls",
        json={
            "source_blog_id": finished.json()["id"],
            "normalized_url": "https://alpha.example/",
            "status": "success",
        },
    )
    model_filtered_raw = client.post(
        "/internal/raw-discovered-urls",
        json={
            "source_blog_id": finished.json()["id"],
            "normalized_url": "https://model-filtered.example/",
            "status": "model:model_consensus_all_non_blog",
        },
    )
    rule_filtered_raw = client.post(
        "/internal/raw-discovered-urls",
        json={
            "source_blog_id": finished.json()["id"],
            "normalized_url": "https://rule-filtered.example/",
            "status": "rule:blocked_tld",
        },
    )
    assert accepted_raw.status_code == 200
    assert model_filtered_raw.status_code == 200
    assert rule_filtered_raw.status_code == 200

    candidates = client.get("/internal/blog-labeling/candidates", params={"labeled": "false"})
    assert candidates.status_code == 200
    assert [row["url"] for row in candidates.json()["items"]] == [
        "https://model-filtered.example/",
        "https://alpha.example/",
    ]
    assert candidates.json()["items"][0]["labels"] == []
    assert candidates.json()["filters"]["labeled"] is False

    create_blog = client.post("/internal/blog-labeling/tags", json={"name": "blog"})
    create_official = client.post("/internal/blog-labeling/tags", json={"name": "official"})
    assert create_blog.status_code == 200
    assert create_official.status_code == 200

    tags = client.get("/internal/blog-labeling/tags")
    assert tags.status_code == 200
    assert [row["slug"] for row in tags.json()] == [
        "blog",
        "company",
        "other",
        "unknown",
        "official",
        "government",
    ]

    put_label = client.put(
        f"/internal/blog-labeling/labels/{candidates.json()['items'][0]['id']}",
        json={"label_id": {str(create_blog.json()["id"]): 10, str(create_official.json()["id"]): 1}},
    )
    assert put_label.status_code == 200
    assert put_label.json()["label_id"] == {"1": 10, "5": 1}
    assert put_label.json()["label_slugs"] == ["blog", "official"]

    counts = client.get("/internal/blog-labeling/counts")
    assert counts.status_code == 200
    assert counts.json()["total_labeled"] == 1
    assert counts.json()["by_label"]["blog"] == 1
    assert counts.json()["by_label"]["official"] == 1

    candidates_after_label = client.get("/internal/blog-labeling/candidates", params={"labeled": "false"})
    assert candidates_after_label.status_code == 200
    assert [row["url"] for row in candidates_after_label.json()["items"]] == ["https://alpha.example/"]

    export_csv = client.get("/internal/blog-labeling/export")
    assert export_csv.status_code == 404

    parquet_status = client.get("/internal/blog-labeling/parquet-status")
    assert parquet_status.status_code == 200
    assert parquet_status.json()["total_labeled"] == 2
    assert parquet_status.json()["saved_count"] == 0
    assert parquet_status.json()["missing_count"] == 2

    parquet_sync = client.post("/internal/blog-labeling/parquet-sync")
    assert parquet_sync.status_code == 200
    assert parquet_sync.json()["saved_count"] == 2
    assert parquet_sync.json()["missing_count"] == 0

    parquet_export = client.get("/internal/blog-labeling/parquet-export")
    assert parquet_export.status_code == 200
    assert parquet_export.headers["content-type"].startswith("application/vnd.apache.parquet")
    assert parquet_export.headers["x-heyblog-label-saved-count"] == "2"

    user_label = client.post(
        f"/internal/blogs/{finished.json()['id']}/user-labels",
        json={"label": "blog"},
    )
    assert user_label.status_code == 200
    assert user_label.json()["label_id"] == {"1": 1}
    assert user_label.json()["label_slugs"] == ["blog"]
    switched_user_label = client.post(
        f"/internal/blogs/{finished.json()['id']}/user-labels",
        json={"label": "other", "previous_label": "blog"},
    )
    assert switched_user_label.status_code == 200
    assert switched_user_label.json()["label_id"] == {"3": 1}
    assert switched_user_label.json()["label_slugs"] == ["other"]
    account = client.post("/internal/users/register", json={"email": "voter@example.com", "password": "long enough"})
    assert account.status_code == 200
    verified_account = client.post(
        "/internal/users/email-verification/confirm",
        json={"token": account.json()["verification_token"]},
    )
    assert verified_account.status_code == 200
    account_user_label = client.post(
        f"/internal/blogs/{finished.json()['id']}/user-labels",
        json={"label": "blog", "user_id": verified_account.json()["id"]},
    )
    assert account_user_label.status_code == 200
    account_user_label_switch = client.post(
        f"/internal/blogs/{finished.json()['id']}/user-labels",
        json={"label": "other", "user_id": verified_account.json()["id"]},
    )
    assert account_user_label_switch.status_code == 200
    selections = client.get(
        f"/internal/users/{verified_account.json()['id']}/label-selections",
        params={"limit": 5},
    )
    assert selections.status_code == 200
    assert selections.json()[0]["label"] == "other"

    labeled = client.get(
        "/internal/blog-labeling/candidates",
        params={"label": "official", "labeled": "true", "sort": "recently_labeled"},
    )
    assert labeled.status_code == 200
    assert [row["id"] for row in labeled.json()["items"]] == [candidates.json()["items"][0]["id"]]
    assert labeled.json()["items"][0]["is_labeled"] is True
    assert [row["slug"] for row in labeled.json()["items"][0]["labels"]] == ["blog", "official"]

    invalid_label = client.post("/internal/blog-labeling/tags", json={"name": "   "})
    assert invalid_label.status_code == 422

    unrelated = client.post(
        "/internal/blogs/upsert",
        json={
            "url": "https://gamma.example/",
            "normalized_url": "https://gamma.example/",
            "domain": "gamma.example",
        },
    )
    assert unrelated.status_code == 200
    conflict = client.put(
        f"/internal/blog-labeling/labels/{unrelated.json()['id']}",
        json={"tag_ids": [create_blog.json()["id"]]},
    )
    assert conflict.status_code == 409

    missing = client.put("/internal/blog-labeling/labels/999", json={"tag_ids": [create_blog.json()["id"]]})
    assert missing.status_code == 404

    unknown_label = client.put(
        f"/internal/blog-labeling/labels/{finished.json()['id']}",
        json={"tag_ids": [999]},
    )
    assert unknown_label.status_code == 422


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

    response = client.replace_blog_link_labels(blog_id=7, tag_ids=[3, 5], title="Temporary")

    assert response == {"ok": True}
    assert stub.put_calls == [("/internal/blog-labeling/labels/7", {"tag_ids": [3, 5], "title": "Temporary"})]
    assert stub.post_calls == []


def test_persistence_http_client_can_manage_blog_label_training_parquet() -> None:
    """The split-service HTTP client should expose parquet status, sync, rebuild, and download."""

    status_payload = {
        "path": "/tmp/blog-label-training.parquet",
        "filename": "blog-label-training.parquet",
        "exists": True,
        "saved_count": 1,
        "total_labeled": 1,
        "missing_count": 0,
        "batch_size": 100,
        "rewritten": False,
        "message": "ok",
        "updated_at": "2026-05-24T00:00:00Z",
    }

    class StubResponse:
        content = b"PAR1"
        headers = {"content-disposition": 'attachment; filename="blog-label-training.parquet"'}

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return status_payload

    class StubClient:
        def __init__(self) -> None:
            self.get_calls: list[str] = []
            self.post_calls: list[tuple[str, dict[str, object]]] = []

        def get(self, path: str, params: dict[str, object] | None = None) -> StubResponse:
            self.get_calls.append(path)
            return StubResponse()

        def post(self, path: str, json: dict[str, object]) -> StubResponse:
            self.post_calls.append((path, json))
            return StubResponse()

    client = PersistenceHttpClient("http://persistence.internal")
    stub = StubClient()
    client.client = stub  # type: ignore[assignment]

    assert client.get_blog_label_training_parquet_status()["saved_count"] == 1
    assert client.sync_blog_label_training_parquet()["missing_count"] == 0
    assert client.rebuild_blog_label_training_parquet()["rewritten"] is False
    parquet_bytes, parquet_headers = client.export_blog_label_training_parquet()

    assert parquet_bytes == b"PAR1"
    assert parquet_headers["content-disposition"] == 'attachment; filename="blog-label-training.parquet"'
    assert stub.get_calls == [
        "/internal/blog-labeling/parquet-status",
        "/internal/blog-labeling/parquet-export",
    ]
    assert stub.post_calls == [
        ("/internal/blog-labeling/parquet-sync", {}),
        ("/internal/blog-labeling/parquet-rebuild", {}),
    ]


def test_persistence_http_client_can_manage_user_auth_and_labels() -> None:
    """The split-service HTTP client should expose user auth helper methods."""

    class StubResponse:
        content = b""
        headers: dict[str, str] = {}

        def __init__(self, payload: object) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return self.payload

    class StubClient:
        def __init__(self) -> None:
            self.get_calls: list[tuple[str, dict[str, object] | None]] = []
            self.post_calls: list[tuple[str, dict[str, object]]] = []

        def get(self, path: str, params: dict[str, object] | None = None, **kwargs: object) -> StubResponse:
            del kwargs
            self.get_calls.append((path, params))
            if path == "/internal/users/me":
                return StubResponse({"id": 7, "email": "user@example.com", "display_name": "user"})
            if path == "/internal/users/7/label-stats":
                return StubResponse({"label_count": 3})
            return StubResponse([])

        def post(self, path: str, json: dict[str, object], **kwargs: object) -> StubResponse:
            del kwargs
            self.post_calls.append((path, json))
            if path == "/internal/users/register":
                return StubResponse({"sent": True, "verification_token": "verify-token"})
            return StubResponse({"token": "token", "user": {"id": 7, "email": "user@example.com"}})

    client = PersistenceHttpClient("http://persistence.internal")
    stub = StubClient()
    client.client = stub  # type: ignore[assignment]

    assert client.register_user(email="user@example.com", password="long enough")["sent"] is True
    assert client.login_user(email="user@example.com", password="long enough")["token"] == "token"
    assert client.get_user_by_session_token(token="token")["id"] == 7
    assert client.list_user_label_selections(user_id=7) == []
    assert client.get_user_label_stats(user_id=7) == {"label_count": 3}
    client.increment_blog_user_label(blog_id=3, label="blog", user_id=7)

    assert stub.post_calls[-1] == ("/internal/blogs/3/user-labels", {"label": "blog", "user_id": 7})
    assert ("/internal/users/me", {"session_token": "token"}) in stub.get_calls
    assert ("/internal/users/7/label-selections", {"limit": 50}) in stub.get_calls
    assert ("/internal/users/7/label-stats", None) in stub.get_calls


def test_persistence_http_client_can_manage_recommendation_data() -> None:
    """The split-service HTTP client should expose recommendation data helpers."""

    class StubResponse:
        def __init__(self, payload: object) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return self.payload

    class StubClient:
        def __init__(self) -> None:
            self.get_calls: list[tuple[str, dict[str, object] | None]] = []
            self.post_calls: list[tuple[str, dict[str, object]]] = []

        def get(self, path: str, params: dict[str, object] | None = None, **kwargs: object) -> StubResponse:
            del kwargs
            self.get_calls.append((path, params))
            return StubResponse({"ok": True})

        def post(self, path: str, json: dict[str, object], **kwargs: object) -> StubResponse:
            del kwargs
            self.post_calls.append((path, json))
            return StubResponse({"ok": True, "items": []})

    client = PersistenceHttpClient("http://persistence.internal")
    stub = StubClient()
    client.client = stub  # type: ignore[assignment]

    client.create_random_recommendation_batch(
        count=9,
        visitor_id="visitor-1",
        session_id="session-1",
        source="random_page",
    )
    client.record_blog_interaction(
        event_uuid="event-1",
        event_type="detail_open",
        blog_id=42,
        visitor_id="visitor-1",
        session_id="session-1",
        entrance_kind="test_detail",
        entrance_url="http://localhost/random",
        request_uuid="request-1",
        impression_id=12,
        position=1,
    )
    assert client.get_blog_recommendation_stats(42) == {"ok": True}
    assert client.get_recommendation_strategy_stats() == {"ok": True}
    assert client.get_admin_hourly_stats(limit=6) == {"ok": True}

    assert stub.post_calls == [
        (
            "/internal/recommendations/random-blog-batches",
            {
                "count": 9,
                "visitor_id": "visitor-1",
                "session_id": "session-1",
                "user_id": None,
                "source": "random_page",
                "page_url": None,
                "context": None,
            },
        ),
        (
            "/internal/recommendation-events",
            {
                "event_uuid": "event-1",
                "event_type": "detail_open",
                "blog_id": 42,
                "visitor_id": "visitor-1",
                "session_id": "session-1",
                "entrance_kind": "test_detail",
                "entrance_url": "http://localhost/random",
                "request_uuid": "request-1",
                "impression_id": 12,
                "position": 1,
                "interaction_order": 1,
                "user_id": None,
                "client_event_at": None,
                "attributes": None,
            },
        ),
    ]
    assert stub.get_calls == [
        ("/internal/blogs/42/recommendation-stats", None),
        ("/internal/recommendation-stats", None),
        ("/internal/admin/hourly-stats", {"limit": 6}),
    ]


def test_backend_routes_forward_recommendation_data_with_optional_user() -> None:
    """Backend public recommendation routes should preserve attribution fields."""

    class RecommendationPersistenceStub:
        def __init__(self) -> None:
            self.batch_payload: dict[str, object] | None = None
            self.event_payload: dict[str, object] | None = None

        def get_user_by_session_token(self, *, token: str) -> dict[str, object] | None:
            assert token == "session-token"
            return {"id": 7, "email": "user@example.com"}

        def create_random_recommendation_batch(self, **kwargs: object) -> dict[str, object]:
            self.batch_payload = kwargs
            return {"request_uuid": "request-1", "items": []}

        def record_blog_interaction(self, **kwargs: object) -> dict[str, object]:
            self.event_payload = kwargs
            return {"event_uuid": kwargs["event_uuid"], "duplicate": False}

        def get_blog_recommendation_stats(self, blog_id: int) -> dict[str, object]:
            return {"blog_id": blog_id, "impressions": 1}

        def get_recommendation_strategy_stats(self) -> dict[str, object]:
            return {"total_requests": 1, "by_strategy": []}

        def get_admin_hourly_stats(self, *, limit: int = 24) -> dict[str, object]:
            return {"limit": limit, "items": []}

    persistence = RecommendationPersistenceStub()
    app = create_backend_app(
        BackendState(
            persistence=persistence,
            crawler=StubCrawler(),
            search=StubSearch(),
            admin_token="secret-token",
        )
    )
    client = TestClient(app)

    batch_response = client.post(
        "/api/recommendations/random-blog-batches",
        headers={"authorization": "Bearer session-token"},
        json={
            "count": 9,
            "visitor_id": "visitor-1",
            "session_id": "session-1",
            "source": "random_page",
        },
    )
    event_response = client.post(
        "/api/recommendation-events",
        headers={"authorization": "Bearer session-token"},
        json={
            "event_uuid": "event-1",
            "event_type": "detail_open",
            "blog_id": 42,
            "visitor_id": "visitor-1",
            "session_id": "session-1",
            "entrance_kind": "test_detail",
            "entrance_url": "http://localhost/random",
            "request_uuid": "request-1",
            "impression_id": 12,
            "position": 1,
        },
    )
    blog_stats = client.get("/api/blogs/42/stats")
    admin_stats = client.get("/api/admin/recommendation-stats", headers=admin_headers())
    admin_hourly_stats = client.get("/api/admin/hourly-stats?limit=6", headers=admin_headers())

    assert batch_response.status_code == 200
    assert event_response.status_code == 200
    assert blog_stats.json() == {"blog_id": 42, "impressions": 1}
    assert admin_stats.json() == {"total_requests": 1, "by_strategy": []}
    assert admin_hourly_stats.json() == {"limit": 6, "items": []}
    assert persistence.batch_payload is not None
    assert persistence.batch_payload["user_id"] == 7
    assert persistence.batch_payload["visitor_id"] == "visitor-1"
    assert persistence.event_payload is not None
    assert persistence.event_payload["user_id"] == 7
    assert persistence.event_payload["event_type"] == "detail_open"
    assert persistence.event_payload["entrance_kind"] == "test_detail"
    assert persistence.event_payload["entrance_url"] == "http://localhost/random"


def test_settings_can_enable_postgres_runtime(tmp_path: Path, monkeypatch) -> None:
    """Environment loading should allow the split runtime to point at Postgres."""
    monkeypatch.setenv("HEYBLOG_DB_DSN", "postgresql://heyblog:heyblog@persistence-db:5432/heyblog")
    monkeypatch.setenv("HEYBLOG_DB_PATH", str(tmp_path / "unused.sqlite"))
    monkeypatch.setenv("HEYBLOG_SEED_PATH", str(tmp_path / "seed.csv"))
    monkeypatch.setenv("HEYBLOG_EXPORT_DIR", str(tmp_path / "exports"))

    settings = Settings.from_env()

    assert settings.db_dsn == "postgresql://heyblog:heyblog@persistence-db:5432/heyblog"


def test_settings_loads_candidate_link_page_limit(monkeypatch) -> None:
    """Environment loading should expose the per-candidate-page link limit."""
    monkeypatch.setenv("HEYBLOG_MAX_CANDIDATE_LINKS_PER_PAGE", "17")

    settings = Settings.from_env()

    assert settings.max_candidate_links_per_page == 17


def test_settings_loads_smtp_email_delivery_configuration(monkeypatch) -> None:
    """Environment loading should expose SMTP lifecycle email settings."""
    monkeypatch.setenv("HEYBLOG_EMAIL_PROVIDER", "smtp")
    monkeypatch.setenv("HEYBLOG_EMAIL_FROM", "no-reply@heyblog.example")
    monkeypatch.setenv("HEYBLOG_EMAIL_DEV_EXPOSE_TOKENS", "false")
    monkeypatch.setenv("HEYBLOG_SMTP_HOST", "smtp.heyblog.example")
    monkeypatch.setenv("HEYBLOG_SMTP_PORT", "465")
    monkeypatch.setenv("HEYBLOG_SMTP_USERNAME", "smtp-user")
    monkeypatch.setenv("HEYBLOG_SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("HEYBLOG_SMTP_USE_TLS", "false")
    monkeypatch.setenv("HEYBLOG_SMTP_USE_SSL", "true")
    monkeypatch.setenv("HEYBLOG_SMTP_TIMEOUT_SECONDS", "3.5")

    settings = Settings.from_env()

    assert settings.email_provider == "smtp"
    assert settings.email_from == "no-reply@heyblog.example"
    assert settings.email_dev_expose_tokens is False
    assert settings.smtp_host == "smtp.heyblog.example"
    assert settings.smtp_port == 465
    assert settings.smtp_username == "smtp-user"
    assert settings.smtp_password == "smtp-password"
    assert settings.smtp_use_tls is False
    assert settings.smtp_use_ssl is True
    assert settings.smtp_timeout_seconds == 3.5


def test_settings_default_runtime_model_root_uses_runtime_resources(monkeypatch) -> None:
    """Environment loading should default runtime model reads to published resources."""
    monkeypatch.delenv("HEYBLOG_DECISION_MODEL_ROOT", raising=False)

    settings = Settings.from_env()

    assert settings.decision_model_root == PROJECT_ROOT / "runtime_resources" / "models" / "url_decision" / "current"


def test_backend_service_preserves_supported_public_api_shape(monkeypatch) -> None:
    """Backend service should preserve the supported public API fields."""
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
            "get_blog_label_training_parquet_status": lambda self: {
                "path": "/tmp/blog-label-training.parquet",
                "filename": "blog-label-training.parquet",
                "exists": True,
                "saved_count": 1,
                "total_labeled": 1,
                "missing_count": 0,
                "batch_size": 100,
                "rewritten": False,
                "message": "已保存 1 条数据，总计有 label 的有 1 条数据。",
                "updated_at": "2026-05-24T00:00:00Z",
            },
            "sync_blog_label_training_parquet": lambda self: {
                "path": "/tmp/blog-label-training.parquet",
                "filename": "blog-label-training.parquet",
                "exists": True,
                "saved_count": 1,
                "total_labeled": 1,
                "missing_count": 0,
                "batch_size": 100,
                "rewritten": False,
                "message": "无需重新保存：已保存 1 条数据，总计有 label 的有 1 条数据。",
                "updated_at": "2026-05-24T00:00:00Z",
            },
            "rebuild_blog_label_training_parquet": lambda self: {
                "path": "/tmp/blog-label-training.parquet",
                "filename": "blog-label-training.parquet",
                "exists": True,
                "saved_count": 1,
                "total_labeled": 1,
                "missing_count": 0,
                "batch_size": 100,
                "rewritten": True,
                "message": "已重置 parquet 文件并重新保存 1 条数据。",
                "updated_at": "2026-05-24T00:00:00Z",
            },
            "export_blog_label_training_parquet": lambda self: (
                b"PAR1",
                {
                    "content-disposition": 'attachment; filename="blog-label-training.parquet"',
                    "x-heyblog-label-saved-count": "1",
                    "x-heyblog-label-total-count": "1",
                },
            ),
            "create_blog_label_tag": lambda self, name: {
                "id": 12,
                "name": name,
                "slug": name.lower(),
                "created_at": "2026-04-05T00:00:00Z",
                "updated_at": "2026-04-05T00:00:00Z",
            },
            "get_blog_label_counts": lambda self: {
                "total_labeled": 2373,
                "by_label": {
                    "blog": 651,
                    "company": 226,
                    "other": 1496,
                    "unknown": 0,
                },
            },
            "replace_blog_link_labels": lambda self, blog_id, tag_ids=None, label_id=None, title=None: {
                "blog_id": blog_id,
                "title": title,
                "label_id": label_id or {str(tag_id): 1 for tag_id in (tag_ids or [])},
                "labels": [
                    {
                        "id": tag_id,
                        "name": f"tag-{tag_id}",
                        "slug": f"tag-{tag_id}",
                        "created_at": "2026-04-05T00:00:00Z",
                        "updated_at": "2026-04-05T00:00:00Z",
                        "labeled_at": "2026-04-05T00:00:00Z",
                    }
                    for tag_id in (tag_ids or [])
                ],
                "label_slugs": [f"tag-{tag_id}" for tag_id in (tag_ids or [])],
                "last_labeled_at": "2026-04-05T00:00:00Z" if (tag_ids or label_id) else None,
                "is_labeled": bool(tag_ids or label_id),
            },
            "register_user": lambda self, email, password: {
                "sent": True,
                "verification_token": "verify-token",
                "expires_at": "2026-06-12T00:00:00Z",
            },
            "login_user": lambda self, email, password: {
                "token": "login-token",
                "expires_at": "2026-06-25T00:00:00Z",
                "user": {
                    "id": 42,
                    "email": email.lower(),
                    "display_name": email.split("@", 1)[0],
                    "created_at": "2026-05-26T00:00:00Z",
                    "updated_at": "2026-05-26T00:00:00Z",
                },
            },
            "get_user_by_session_token": lambda self, token: {
                "id": 42,
                "email": "member@example.com",
                "display_name": "member",
                "created_at": "2026-05-26T00:00:00Z",
                "updated_at": "2026-05-26T00:00:00Z",
            } if token in {"user-token", "login-token"} else None,
            "revoke_user_session": lambda self, token: {"ok": True},
            "get_user_label_stats": lambda self, user_id: {"label_count": 12},
            "list_user_label_selections": lambda self, user_id, limit=50: [
                {
                    "id": 1,
                    "normalized_url": "https://catalog.example.com",
                    "label_id": 1,
                    "label": "blog",
                    "label_name": "blog",
                    "created_at": "2026-05-26T00:00:00Z",
                    "updated_at": "2026-05-26T00:00:00Z",
                    "blog": None,
                }
            ],
            "increment_blog_user_label": lambda self, blog_id, label, previous_label=None, user_id=None: {
                "blog_id": blog_id,
                "label_id": {"1": 1},
                "labels": [
                    {
                        "id": 1,
                        "name": label,
                        "slug": label,
                        "count": 1,
                        "labeled_at": "2026-04-05T00:00:00Z",
                    }
                ],
                "label_slugs": [label],
                "last_labeled_at": "2026-04-05T00:00:00Z",
                "is_labeled": True,
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
            "create_user_seed": lambda self, homepage_url: {
                "status": "QUEUED",
                "blog_id": 44,
                "inserted": True,
                "blog": {
                    "id": 44,
                    "blog_id": 44,
                    "url": homepage_url,
                    "normalized_url": homepage_url,
                    "domain": "queued-user.example",
                    "acceptance_status": "ACCEPTED",
                    "accepted_by": "user",
                    "crawl_status": "WAITING",
                },
            },
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
            "get_filter_stats_by_chain_order": lambda self: {
                "by_filter_reason": {
                    "raw": 3,
                    "rule:same_domain": 2,
                }
            },
            "reset": lambda self: {
                "ok": True,
                "blogs_deleted": 3,
                "edges_deleted": 4,
                "raw_discovered_urls_deleted": 5,
                "logs_deleted": 0,
            },
            "requeue_failed_blogs": lambda self: {"requeued": 7},
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

    filter_stats = client.get("/api/filter-stats")
    assert filter_stats.status_code == 200
    assert filter_stats.json()["by_filter_reason"]["rule:same_domain"] == 2

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

    random_catalog = client.get("/api/blogs/catalog?page_size=9&status=FINISHED&sort=random")
    assert random_catalog.status_code == 200
    assert random_catalog.json()["filters"]["status"] == "FINISHED"
    assert random_catalog.json()["sort"] == "random"

    auth = client.post("/api/auth/register", json={"email": "Member@Example.com", "password": "long enough"})
    assert auth.status_code == 200
    assert auth.json()["sent"] is True
    assert auth.json()["verification_token"] == "verify-token"
    login = client.post("/api/auth/login", json={"email": "member@example.com", "password": "long enough"})
    assert login.status_code == 200
    assert login.json()["token"] == "login-token"
    me = client.get("/api/auth/me", headers={"authorization": "Bearer user-token"})
    assert me.status_code == 200
    assert me.json()["id"] == 42
    selections = client.get("/api/me/label-selections", headers={"authorization": "Bearer user-token"})
    assert selections.status_code == 200
    assert selections.json()[0]["label"] == "blog"
    label_stats = client.get("/api/me/label-stats", headers={"authorization": "Bearer user-token"})
    assert label_stats.status_code == 200
    assert label_stats.json() == {"label_count": 12}

    labeling = client.get("/api/admin/blog-labeling/candidates?page=2&page_size=25&label=official&labeled=true", headers=admin_headers())
    assert labeling.status_code == 200
    assert labeling.json()["page"] == 2
    assert labeling.json()["filters"]["label"] == "official"
    assert labeling.json()["filters"]["labeled"] == "true"
    assert labeling.json()["available_tags"][0]["slug"] == "blog"

    label_counts = client.get("/api/admin/blog-labeling/counts", headers=admin_headers())
    assert label_counts.status_code == 200
    assert label_counts.json() == {
        "total_labeled": 2373,
        "by_label": {
            "blog": 651,
            "company": 226,
            "other": 1496,
            "unknown": 0,
        },
    }

    parquet_status = client.get("/api/admin/blog-labeling/parquet-status", headers=admin_headers())
    assert parquet_status.status_code == 200
    assert parquet_status.json()["saved_count"] == 1

    parquet_sync = client.post("/api/admin/blog-labeling/parquet-sync", headers=admin_headers())
    assert parquet_sync.status_code == 200
    assert parquet_sync.json()["missing_count"] == 0

    parquet_rebuild = client.post("/api/admin/blog-labeling/parquet-rebuild", headers=admin_headers())
    assert parquet_rebuild.status_code == 200
    assert parquet_rebuild.json()["rewritten"] is True

    parquet_export = client.get("/api/admin/blog-labeling/parquet-export", headers=admin_headers())
    assert parquet_export.status_code == 200
    assert parquet_export.content == b"PAR1"
    assert parquet_export.headers["content-type"].startswith("application/vnd.apache.parquet")

    tag_create = client.post("/api/admin/blog-labeling/tags", json={"name": "government"}, headers=admin_headers())
    assert tag_create.status_code == 200
    assert tag_create.json()["slug"] == "government"

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        request = httpx.Request("GET", url)
        assert kwargs["follow_redirects"] is True
        assert kwargs["timeout"] == 5.0
        return httpx.Response(
            200,
            request=request,
            text="<html><head><title>Raw Only Title</title></head><body></body></html>",
        )

    monkeypatch.setattr("backend.main.httpx.get", fake_get)
    title_preview = client.post(
        "/api/admin/blog-labeling/title-preview",
        json={"url": "https://raw-only.example/"},
        headers=admin_headers(),
    )
    assert title_preview.status_code == 200
    assert title_preview.json() == {"url": "https://raw-only.example/", "title": "Raw Only Title"}

    label_update = client.put(
        "/api/admin/blog-labeling/labels/3",
        json={"tag_ids": [10, 11], "title": "Temporary Label Title"},
        headers=admin_headers(),
    )
    assert label_update.status_code == 200
    assert label_update.json()["blog_id"] == 3
    assert label_update.json()["title"] == "Temporary Label Title"
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

    requeue = client.post("/api/admin/blogs/requeue-failed", headers=admin_headers())
    assert requeue.status_code == 200
    assert requeue.json() == {"requeued": 7}

    user_seed = client.post(
        "/api/blogs/user-seeds",
        json={"homepage_url": "https://queued-user.example/"},
    )
    assert user_seed.status_code == 200
    assert user_seed.json()["blog_id"] == 44
    assert user_seed.json()["blog"]["accepted_by"] == "user"
    assert user_seed.json()["blog"]["crawl_status"] == "WAITING"

    lookup = client.get("/api/blogs/lookup?url=https://queued.example/")
    assert lookup.status_code == 200
    assert lookup.json()["match_reason"] == "identity_key"
    assert lookup.json()["items"][0]["id"] == 3

    reset = client.post("/api/admin/database/reset", headers=admin_headers())
    assert reset.status_code == 200
    assert reset.json()["blogs_deleted"] == 3
    assert reset.json()["edges_deleted"] == 4
    assert reset.json()["raw_discovered_urls_deleted"] == 5
    assert reset.json()["search_reindexed"] is True
    assert search.reindex_calls == 3


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/admin/crawl/run?max_nodes=2", None),
        ("/api/admin/runtime/run-batch", {"max_nodes": 3}),
    ],
)
def test_backend_preserves_crawler_capacity_conflict_detail(
    path: str,
    body: dict[str, int] | None,
) -> None:
    """Backend should relay crawler raw-limit conflicts without reindexing search."""

    class CapacityBlockedCrawler(StubCrawler):
        def _raise_capacity_conflict(self) -> None:
            request = httpx.Request("POST", "http://crawler/internal/runtime/start")
            response = httpx.Response(
                409,
                request=request,
                json={
                    "detail": {
                        "reason": "raw_discovered_url_limit_reached",
                        "raw_count": 1_000_000,
                        "limit": 1_000_000,
                    }
                },
            )
            raise httpx.HTTPStatusError("raw limit reached", request=request, response=response)

        def run(self, max_nodes: int | None = None) -> dict[str, int | None]:
            self._raise_capacity_conflict()

        def run_batch(self, max_nodes: int) -> dict[str, object]:
            self._raise_capacity_conflict()

    search = StubSearch()
    app = create_backend_app(
        BackendState(
            persistence=object(),
            crawler=CapacityBlockedCrawler(),
            search=search,
            admin_token="secret-token",
        )
    )
    client = TestClient(app)

    if body is None:
        response = client.post(path, headers=admin_headers())
    else:
        response = client.post(path, json=body, headers=admin_headers())

    assert response.status_code == 409
    assert response.json()["detail"]["reason"] == "raw_discovered_url_limit_reached"
    assert response.json()["detail"]["raw_count"] == 1_000_000
    assert search.reindex_calls == 0


def test_backend_service_removes_legacy_public_routes() -> None:
    """Backend service should not expose obsolete raw public routes."""
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
        },
    )()
    app = create_backend_app(
        BackendState(
            persistence=persistence,
            crawler=StubCrawler(),
            search=StubSearch(),
            admin_token="secret-token",
        )
    )
    client = TestClient(app)

    assert client.get("/api/blogs").status_code == 404
    assert client.get("/api/edges").status_code == 404
    assert client.get("/api/graph").status_code == 404
    assert client.get("/api/logs").status_code == 404
    assert client.get("/api/search?q=blog").status_code == 404


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

        def replace_blog_link_labels(
            self,
            *,
            blog_id: int,
            tag_ids: list[int] | None = None,
            label_id: dict[str, int] | None = None,
            title: str | None = None,
        ) -> dict[str, object]:
            del tag_ids, label_id, title
            request = httpx.Request("PUT", f"http://persistence/internal/blog-labeling/labels/{blog_id}")
            response = httpx.Response(
                409,
                request=request,
                json={"detail": "blog_labeling_requires_finished_blog"},
            )
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
            return {"ok": True, "blogs_deleted": 0, "edges_deleted": 0, "raw_discovered_urls_deleted": 0, "logs_deleted": 0}

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
    assert export_response.status_code == 404


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
            return {"ok": True, "blogs_deleted": 0, "edges_deleted": 0, "raw_discovered_urls_deleted": 0, "logs_deleted": 0}

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


def test_backend_lookup_and_user_seed_surface_upstream_validation_errors() -> None:
    """Public lookup and user seed endpoints should preserve upstream failures."""

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

        def create_user_seed(self, *, homepage_url: str) -> dict[str, object]:
            request = httpx.Request("POST", "http://persistence/internal/user-seeds")
            response = httpx.Response(422, request=request, json={"detail": "rule:blocked_tld"})
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
            return {"ok": True, "blogs_deleted": 0, "edges_deleted": 0, "raw_discovered_urls_deleted": 0, "logs_deleted": 0}

    app = create_backend_app(
        BackendState(persistence=LookupValidationStub(), crawler=StubCrawler(), search=StubSearch())
    )
    client = TestClient(app)

    lookup = client.get("/api/blogs/lookup?url=notaurl")
    assert lookup.status_code == 422
    assert lookup.json()["detail"] == "Unsupported homepage URL"

    user_seed = client.post("/api/blogs/user-seeds", json={"homepage_url": "https://blog.sayori.org/"})
    assert user_seed.status_code == 422
    assert user_seed.json()["detail"] == "rule:blocked_tld"


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
            return {"ok": True, "blogs_deleted": 0, "edges_deleted": 0, "raw_discovered_urls_deleted": 0, "logs_deleted": 0}

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
                "raw_discovered_urls_deleted": 0,
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


def test_backend_admin_routes_require_verified_admin_session_role() -> None:
    """Admin APIs should reject non-admin sessions even when called directly."""

    class PersistenceStub:
        def stats(self) -> dict[str, object]:
            return {}

        def get_user_by_session_token(self, *, token: str) -> dict[str, object] | None:
            users = {
                "plain-user-token": {
                    "id": 1,
                    "role": "user",
                    "is_active": True,
                    "email_verified": True,
                },
                "unverified-admin-token": {
                    "id": 2,
                    "role": "admin",
                    "is_active": True,
                    "email_verified": False,
                },
                "admin-session-token": {
                    "id": 3,
                    "role": "admin",
                    "is_active": True,
                    "email_verified": True,
                },
            }
            return users.get(token)

    app = create_backend_app(
        BackendState(
            persistence=PersistenceStub(),
            crawler=StubCrawler(),
            search=StubSearch(),
            admin_token="secret-token",
        )
    )
    client = TestClient(app)

    user_response = client.get("/api/admin/runtime/status", headers=admin_headers("plain-user-token"))
    assert user_response.status_code == 403
    assert user_response.json()["detail"] == "admin_auth_forbidden"

    unverified_response = client.get("/api/admin/runtime/status", headers=admin_headers("unverified-admin-token"))
    assert unverified_response.status_code == 403
    assert unverified_response.json()["detail"] == "admin_auth_forbidden"

    admin_response = client.get("/api/admin/runtime/status", headers=admin_headers("admin-session-token"))
    assert admin_response.status_code == 200
    assert admin_response.json()["runner_status"] == "idle"


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


def test_frontend_api_proxy_preserves_cache_control(tmp_path: Path, monkeypatch) -> None:
    """Frontend API proxy should keep cache headers for proxied icon images."""

    class AsyncClientStub:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> "AsyncClientStub":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def request(self, method: str, target: str, **kwargs: object) -> httpx.Response:
            assert method == "GET"
            assert target == "http://backend:8000/api/icons/proxy"
            assert self.timeout == 60.0
            return httpx.Response(
                200,
                content=b"icon",
                headers={"content-type": "image/png", "cache-control": "public, max-age=86400"},
                request=httpx.Request(method, target),
            )

    monkeypatch.setattr("frontend.server.httpx.AsyncClient", AsyncClientStub)
    settings = Settings(
        db_path=tmp_path / "heyblog.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        backend_base_url="http://backend:8000",
    )
    app = create_frontend_app(settings)
    client = TestClient(app)

    response = client.get("/api/icons/proxy", params={"url": "https://icons.example.com/favicon.png"})

    assert response.status_code == 200
    assert response.content == b"icon"
    assert response.headers["content-type"].startswith("image/png")
    assert response.headers["cache-control"] == "public, max-age=86400"


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


def test_frontend_service_serves_spa_entry_for_deep_links_but_not_missing_assets(tmp_path: Path, monkeypatch) -> None:
    """SPA deep links should resolve to index while unknown asset paths still 404."""
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

    deep_link = client.get("/about")
    favicon = client.get("/favicon.ico")
    missing_asset = client.get("/missing.png")

    assert deep_link.status_code == 200
    assert "Built App" in deep_link.text
    assert favicon.status_code == 200
    assert favicon.headers["content-type"].startswith("image/svg+xml")
    assert missing_asset.status_code == 404


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

    response = client.put(
        "/api/admin/blog-labeling/labels/1",
        json={"tag_ids": [10, 11], "title": "Temporary"},
        headers=admin_headers(),
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert captured["headers"].pop("x-request-id")
    assert captured == {
        "timeout": 60.0,
        "method": "PUT",
        "url": "http://backend:8000/api/admin/blog-labeling/labels/1",
        "params": {},
        "content": b'{"tag_ids":[10,11],"title":"Temporary"}',
        "headers": {
            "content-type": "application/json",
            "authorization": "Bearer secret-token",
        },
    }


def test_frontend_service_does_not_forward_empty_authorization_headers(tmp_path: Path, monkeypatch) -> None:
    """Frontend proxy should omit authorization when the caller did not provide one."""

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

    response = client.post("/api/blogs/user-seeds", json={"homepage_url": "https://blog.example.com"})

    assert response.status_code == 200
    assert captured["headers"].pop("x-request-id")
    assert captured["headers"] == {"content-type": "application/json"}
