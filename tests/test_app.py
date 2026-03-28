"""Integration tests for API endpoints and settings bootstrap."""

from pathlib import Path

from _pytest.monkeypatch import MonkeyPatch
from fastapi.testclient import TestClient

from app.main import create_app
from app.state import build_app_state
from shared.config import Settings


def build_test_client(tmp_path: Path) -> TestClient:
    """Create a test client backed by an isolated temporary database."""
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
    return TestClient(create_app(state))


def test_bootstrap_and_status_endpoint(tmp_path: Path) -> None:
    """Verify bootstrap import count and status counters."""
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
    """Verify graph endpoint returns seeded nodes and no edges initially."""
    client = build_test_client(tmp_path)
    client.post("/api/crawl/bootstrap")

    graph = client.get("/api/graph")
    assert graph.status_code == 200
    payload = graph.json()
    assert len(payload["nodes"]) == 2
    assert payload["edges"] == []


def test_bootstrap_counts_only_new_rows_on_repeat(tmp_path: Path) -> None:
    """Verify repeated bootstrap only imports new seed rows."""
    client = build_test_client(tmp_path)

    first = client.post("/api/crawl/bootstrap")
    second = client.post("/api/crawl/bootstrap")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["imported"] == 2
    assert second.json()["imported"] == 0


def test_settings_from_env_uses_string_user_agent(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Verify environment loading always resolves user_agent as a string."""
    monkeypatch.delenv("HEYBLOG_USER_AGENT", raising=False)
    monkeypatch.setenv("HEYBLOG_DB_PATH", str(tmp_path / "db.sqlite"))
    monkeypatch.setenv("HEYBLOG_SEED_PATH", str(tmp_path / "seed.csv"))
    monkeypatch.setenv("HEYBLOG_EXPORT_DIR", str(tmp_path / "exports"))

    settings = Settings.from_env()

    assert isinstance(settings.user_agent, str)
    assert settings.user_agent.startswith("HeyBlogBot/")


def test_panel_route_returns_html(tmp_path: Path) -> None:
    """Verify the operator panel endpoint serves HTML content."""
    client = build_test_client(tmp_path)

    response = client.get("/panel")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "HeyBlog Operator Console" in response.text
