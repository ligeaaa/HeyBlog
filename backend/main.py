"""Public backend service that aggregates internal services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shared.config import Settings
from shared.http_clients.crawler_http import CrawlerHttpClient
from shared.http_clients.persistence_http import PersistenceHttpClient
from shared.http_clients.search_http import SearchHttpClient


@dataclass(slots=True)
class BackendState:
    """State container for the backend service."""

    persistence: Any
    crawler: Any
    search: Any


class RunBatchRequest(BaseModel):
    max_nodes: int


def build_backend_state(settings: Settings | None = None) -> BackendState:
    """Build the backend service state."""
    resolved = settings or Settings.from_env()
    return BackendState(
        persistence=PersistenceHttpClient(
            resolved.persistence_base_url,
            timeout_seconds=resolved.request_timeout_seconds,
        ),
        crawler=CrawlerHttpClient(
            resolved.crawler_base_url,
            timeout_seconds=max(resolved.request_timeout_seconds, 60.0),
        ),
        search=SearchHttpClient(
            resolved.search_base_url,
            timeout_seconds=resolved.request_timeout_seconds,
        ),
    )


def create_app(state: BackendState | None = None) -> FastAPI:
    """Create the public backend app."""
    app = FastAPI(title="HeyBlog Backend Service", version="0.1.0")
    app.state.backend_state = state or build_backend_state()

    def get_state() -> BackendState:
        return app.state.backend_state

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "name": "HeyBlog Backend",
            "status": "/api/status",
            "panel": "served-by-frontend",
        }

    @app.get("/internal/health")
    def health() -> dict[str, str]:
        state = get_state()
        try:
            # Probe the three upstream services the backend must aggregate before
            # we report the backend as healthy to Compose or external checks.
            state.persistence.stats()
            state.crawler.runtime_status()
            state.search.search("")
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail="upstream_unavailable") from exc
        return {"status": "ok"}

    @app.get("/api/status")
    def get_status() -> dict[str, Any]:
        stats = get_state().persistence.stats()
        runtime = get_state().crawler.runtime_status()
        return {
            "is_running": runtime["runner_status"] in {"starting", "running", "stopping"},
            "pending_tasks": stats["pending_tasks"],
            "processing_tasks": stats["processing_tasks"],
            "finished_tasks": stats["finished_tasks"],
            "failed_tasks": stats["failed_tasks"],
            "total_blogs": stats["total_blogs"],
            "total_edges": stats["total_edges"],
        }

    @app.get("/api/blogs")
    def get_blogs() -> list[dict[str, Any]]:
        return get_state().persistence.list_blogs()

    @app.get("/api/blogs/catalog")
    def get_blogs_catalog(
        page: int = 1,
        page_size: int = 50,
        site: str | None = None,
        url: str | None = None,
        status: str | None = None,
        q: str | None = None,
        sort: str = "id_desc",
        has_title: str | None = None,
        has_icon: str | None = None,
        min_connections: str | None = None,
    ) -> dict[str, Any]:
        try:
            return get_state().persistence.list_blogs_catalog(
                page=page,
                page_size=page_size,
                site=site,
                url=url,
                status=status,
                q=q,
                sort=sort,
                has_title=has_title,
                has_icon=has_icon,
                min_connections=min_connections,
            )
        except httpx.HTTPStatusError as exc:
            detail: Any = "upstream_error"
            try:
                detail = exc.response.json().get("detail", detail)
            except Exception:  # noqa: BLE001
                pass
            raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc

    @app.get("/api/blogs/{blog_id}")
    def get_blog(blog_id: int) -> dict[str, Any]:
        try:
            blog = get_state().persistence.get_blog_detail(blog_id)
        except httpx.HTTPStatusError as exc:
            detail: Any = "upstream_error"
            try:
                detail = exc.response.json().get("detail", detail)
            except Exception:  # noqa: BLE001
                pass
            if exc.response.status_code == 404:
                detail = "Blog not found"
            raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
        if blog is None:
            raise HTTPException(status_code=404, detail="Blog not found")
        return blog

    @app.get("/api/edges")
    def get_edges() -> list[dict[str, Any]]:
        return get_state().persistence.list_edges()

    @app.get("/api/graph")
    def get_graph() -> dict[str, Any]:
        return get_state().persistence.graph()

    @app.get("/api/graph/views/core")
    def get_graph_view(
        strategy: str = "degree",
        limit: int = 180,
        sample_mode: str = "off",
        sample_value: float | None = None,
        sample_seed: int = 7,
    ) -> dict[str, Any]:
        return get_state().persistence.graph_view(
            strategy=strategy,
            limit=limit,
            sample_mode=sample_mode,
            sample_value=sample_value,
            sample_seed=sample_seed,
        )

    @app.get("/api/graph/nodes/{blog_id}/neighbors")
    def get_graph_neighbors(blog_id: int, hops: int = 1, limit: int = 120) -> dict[str, Any]:
        return get_state().persistence.graph_neighbors(blog_id, hops=hops, limit=limit)

    @app.get("/api/graph/snapshots/latest")
    def get_latest_graph_snapshot() -> dict[str, Any]:
        return get_state().persistence.latest_graph_snapshot()

    @app.get("/api/graph/snapshots/{version}")
    def get_graph_snapshot(version: str) -> dict[str, Any]:
        return get_state().persistence.graph_snapshot(version)

    @app.get("/api/stats")
    def get_stats() -> dict[str, Any]:
        return get_state().persistence.stats()

    @app.get("/api/logs")
    def get_logs() -> list[dict[str, Any]]:
        return get_state().persistence.list_logs()

    @app.post("/api/crawl/bootstrap")
    def bootstrap() -> dict[str, Any]:
        return get_state().crawler.bootstrap()

    @app.post("/api/crawl/run")
    def run_crawl(max_nodes: int | None = None) -> dict[str, Any]:
        result = get_state().crawler.run(max_nodes=max_nodes)
        try:
            get_state().search.reindex()
        except Exception:  # noqa: BLE001
            pass
        return result

    @app.get("/api/search")
    def search(q: str, kind: str = "all", limit: int = 10) -> dict[str, Any]:
        try:
            return get_state().search.search(q, kind=kind, limit=limit)
        except httpx.HTTPStatusError as exc:
            detail: Any = "upstream_error"
            try:
                detail = exc.response.json().get("detail", detail)
            except Exception:  # noqa: BLE001
                pass
            raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc

    @app.get("/api/runtime/status")
    def runtime_status() -> dict[str, Any]:
        return get_state().crawler.runtime_status()

    @app.get("/api/runtime/current")
    def runtime_current() -> dict[str, Any]:
        return get_state().crawler.current()

    @app.post("/api/runtime/start")
    def runtime_start() -> dict[str, Any]:
        return get_state().crawler.start()

    @app.post("/api/runtime/stop")
    def runtime_stop() -> dict[str, Any]:
        return get_state().crawler.stop()

    @app.post("/api/runtime/run-batch")
    def runtime_run_batch(payload: RunBatchRequest) -> dict[str, Any]:
        result = get_state().crawler.run_batch(payload.max_nodes)
        try:
            get_state().search.reindex()
        except Exception:  # noqa: BLE001
            pass
        return result

    @app.post("/api/database/reset")
    def reset_database() -> dict[str, Any]:
        runtime = get_state().crawler.runtime_status()
        if runtime.get("runner_status") in {"starting", "running", "stopping"}:
            raise HTTPException(status_code=409, detail="crawler_busy")

        result = get_state().persistence.reset()
        try:
            result["search"] = get_state().search.reindex()
            result["search_reindexed"] = True
        except Exception as exc:  # noqa: BLE001
            result["search"] = None
            result["search_reindexed"] = False
            result["search_error"] = str(exc)
        return result

    return app


app = create_app()
