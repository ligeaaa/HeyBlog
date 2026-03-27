"""Public backend service that aggregates internal services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, HTTPException

from app.clients.crawler_http import CrawlerHttpClient
from app.clients.persistence_http import PersistenceHttpClient
from app.clients.search_http import SearchHttpClient
from app.config import Settings


@dataclass(slots=True)
class BackendState:
    """State container for the backend service."""

    persistence: Any
    crawler: Any
    search: Any


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

    @app.get("/api/status")
    def get_status() -> dict[str, Any]:
        stats = get_state().persistence.stats()
        return {
            "is_running": False,
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

    @app.get("/api/blogs/{blog_id}")
    def get_blog(blog_id: int) -> dict[str, Any]:
        blog = get_state().persistence.get_blog(blog_id)
        if blog is None:
            raise HTTPException(status_code=404, detail="Blog not found")
        blog["outgoing_edges"] = [
            edge for edge in get_state().persistence.list_edges() if edge["from_blog_id"] == blog_id
        ]
        return blog

    @app.get("/api/edges")
    def get_edges() -> list[dict[str, Any]]:
        return get_state().persistence.list_edges()

    @app.get("/api/graph")
    def get_graph() -> dict[str, Any]:
        return get_state().persistence.graph()

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
    def search(q: str) -> dict[str, Any]:
        return get_state().search.search(q)

    return app


app = create_app()

