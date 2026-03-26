from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import build_router
from app.config import Settings
from app.state import build_app_state


def build_test_client(tmp_path: Path) -> TestClient:
    seed_path = tmp_path / "seed.csv"
    seed_path.write_text(
        "url\nhttps://blog.elykia.cn/\nhttps://www.qladgk.com/\n",
        encoding="utf-8",
    )
    settings = Settings(
        db_path=tmp_path / "heyblog.sqlite",
        seed_path=seed_path,
        export_dir=tmp_path / "exports",
    )
    state = build_app_state(settings)
    app = FastAPI(title="HeyBlog Test")
    app.include_router(build_router(state))
    return TestClient(app)


def test_bootstrap_and_status_endpoint(tmp_path: Path) -> None:
    client = build_test_client(tmp_path)

    bootstrap = client.post("/api/crawl/bootstrap")
    assert bootstrap.status_code == 200
    assert bootstrap.json()["imported"] == 2

    status = client.get("/api/status")
    assert status.status_code == 200
    payload = status.json()
    assert payload["pending_tasks"] == 2
    assert payload["total_blogs"] == 2


def test_graph_endpoint_returns_nodes_and_edges(tmp_path: Path) -> None:
    client = build_test_client(tmp_path)
    client.post("/api/crawl/bootstrap")

    graph = client.get("/api/graph")
    assert graph.status_code == 200
    payload = graph.json()
    assert len(payload["nodes"]) == 2
    assert payload["edges"] == []


def test_bootstrap_counts_only_new_rows_on_repeat(tmp_path: Path) -> None:
    client = build_test_client(tmp_path)

    first = client.post("/api/crawl/bootstrap")
    second = client.post("/api/crawl/bootstrap")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["imported"] == 2
    assert second.json()["imported"] == 0


def test_settings_from_env_uses_string_user_agent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("HEYBLOG_USER_AGENT", raising=False)
    monkeypatch.setenv("HEYBLOG_DB_PATH", str(tmp_path / "db.sqlite"))
    monkeypatch.setenv("HEYBLOG_SEED_PATH", str(tmp_path / "seed.csv"))
    monkeypatch.setenv("HEYBLOG_EXPORT_DIR", str(tmp_path / "exports"))

    settings = Settings.from_env()

    assert isinstance(settings.user_agent, str)
    assert settings.user_agent.startswith("HeyBlogBot/")


def test_bootstrap_is_idempotent(tmp_path: Path) -> None:
    client = build_test_client(tmp_path)

    first = client.post("/api/crawl/bootstrap")
    second = client.post("/api/crawl/bootstrap")
    status = client.get("/api/status")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["imported"] == 2
    assert second.json()["imported"] == 0
    assert status.json()["total_blogs"] == 2
