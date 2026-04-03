"""Regression tests for crawler service entrypoints and compatibility exports."""

from __future__ import annotations

from fastapi.testclient import TestClient

from crawler.main import CrawlerState
from crawler.main import RunBatchRequest
from crawler.main import create_app
from services.crawler.main import CrawlerState as ShimCrawlerState
from services.crawler.main import RunBatchRequest as ShimRunBatchRequest
from services.crawler.main import app as shim_app
from services.crawler.main import build_crawler_state as shim_build_crawler_state
from services.crawler.main import create_app as shim_create_app


class StubPipeline:
    """Exercise crawler HTTP handlers without touching real persistence."""

    def bootstrap_seeds(self) -> dict[str, object]:
        return {"seed_path": "seed.csv", "imported": 2}

    def run_once(self, max_nodes: int | None = None) -> dict[str, object]:
        return {
            "processed": max_nodes or 1,
            "discovered": 3,
            "failed": 0,
            "exports": {"graph_json": "graph.json"},
        }


class StubRuntime:
    """Return fixed payloads for runtime endpoints."""

    def status(self) -> dict[str, object]:
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
        return {
            "runner_status": "idle",
            "active_run_id": None,
            "current_blog_id": 10,
            "current_url": "https://blog.example.com/",
            "current_stage": "crawling",
            "last_started_at": "2026-04-03T00:00:00Z",
            "last_error": None,
        }

    def start(self) -> dict[str, object]:
        payload = self.status()
        payload["runner_status"] = "running"
        return payload

    def stop(self) -> dict[str, object]:
        payload = self.status()
        payload["runner_status"] = "stopping"
        return payload

    def run_batch(self, max_nodes: int) -> dict[str, object]:
        return {
            "accepted": True,
            "mode": "batch",
            "result": {"processed": max_nodes, "discovered": 1, "failed": 0, "exports": {}},
            "runtime": self.status(),
        }


def test_crawler_service_routes_preserve_payload_shapes() -> None:
    """Crawler HTTP service should keep its public internal route contract stable."""
    app = create_app(CrawlerState(pipeline=StubPipeline(), runtime=StubRuntime()))
    client = TestClient(app)

    assert client.get("/internal/health").json() == {"status": "ok"}
    assert client.post("/internal/crawl/bootstrap").json() == {"seed_path": "seed.csv", "imported": 2}
    assert client.post("/internal/crawl/run?max_nodes=5").json() == {
        "processed": 5,
        "discovered": 3,
        "failed": 0,
        "exports": {"graph_json": "graph.json"},
    }
    assert client.get("/internal/runtime/status").json()["runner_status"] == "idle"
    assert client.get("/internal/runtime/current").json()["current_blog_id"] == 10
    assert client.post("/internal/runtime/start").json()["runner_status"] == "running"
    assert client.post("/internal/runtime/stop").json()["runner_status"] == "stopping"
    assert client.post("/internal/runtime/run-batch", json={"max_nodes": 4}).json()["result"] == {
        "processed": 4,
        "discovered": 1,
        "failed": 0,
        "exports": {},
    }


def test_services_crawler_main_remains_a_compatibility_shim() -> None:
    """The split-service entrypoint should keep re-exporting crawler.main symbols."""
    assert ShimCrawlerState is CrawlerState
    assert ShimRunBatchRequest is RunBatchRequest
    assert shim_create_app is create_app
    assert callable(shim_build_crawler_state)
    assert shim_app is not None

