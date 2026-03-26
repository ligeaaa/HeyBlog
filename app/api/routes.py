"""Register API routes used by the crawler operator panel."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException

from app.state import AppState


def build_router(get_state: Callable[[], AppState]) -> APIRouter:
    """Build the API router bound to an application state provider."""
    router = APIRouter(prefix="/api")

    @router.get("/status")
    def get_status() -> dict[str, Any]:
        """Return high-level runtime status counters."""
        state = get_state()
        return state.stats_service.status()

    @router.get("/blogs")
    def get_blogs() -> list[dict[str, Any]]:
        """List all known blogs in crawl order."""
        state = get_state()
        return state.repository.list_blogs()

    @router.get("/blogs/{blog_id}")
    def get_blog(blog_id: int) -> dict[str, Any]:
        """Return a single blog record and its outgoing edges."""
        state = get_state()
        blog = state.repository.get_blog(blog_id)
        if blog is None:
            raise HTTPException(status_code=404, detail="Blog not found")
        blog["outgoing_edges"] = [
            edge for edge in state.repository.list_edges() if edge["from_blog_id"] == blog_id
        ]
        return blog

    @router.get("/edges")
    def get_edges() -> list[dict[str, Any]]:
        """List all graph edges discovered by the crawler."""
        state = get_state()
        return state.repository.list_edges()

    @router.get("/graph")
    def get_graph() -> dict[str, Any]:
        """Return a graph payload containing nodes and edges."""
        state = get_state()
        return state.graph_service.graph()

    @router.get("/stats")
    def get_stats() -> dict[str, Any]:
        """Return aggregated crawl statistics."""
        state = get_state()
        return state.stats_service.stats()

    @router.get("/logs")
    def get_logs() -> list[dict[str, Any]]:
        """Return recent crawler logs."""
        state = get_state()
        return state.repository.list_logs()

    @router.post("/crawl/bootstrap")
    def bootstrap() -> dict[str, Any]:
        """Import initial seed URLs into the queue."""
        state = get_state()
        return state.pipeline.bootstrap_seeds()

    @router.post("/crawl/run")
    def run_crawl(max_nodes: int | None = None) -> dict[str, Any]:
        """Run one crawl batch with an optional node limit."""
        state = get_state()
        return state.pipeline.run_once(max_nodes=max_nodes)

    return router
