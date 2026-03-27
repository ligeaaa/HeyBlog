"""Persistence service exposing repository operations over HTTP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from persistence_api.repository import RepositoryProtocol
from persistence_api.repository import build_repository
from shared.config import Settings
from backend.graph_service import GraphService
from backend.stats_service import StatsService


@dataclass(slots=True)
class PersistenceState:
    """State container for the persistence service."""

    repository: RepositoryProtocol
    graph_service: GraphService
    stats_service: StatsService


class UpsertBlogRequest(BaseModel):
    url: str
    normalized_url: str
    domain: str
    depth: int
    source_blog_id: int | None


class BlogResultRequest(BaseModel):
    crawl_status: str
    status_code: int | None
    friend_links_count: int


class AddEdgeRequest(BaseModel):
    from_blog_id: int
    to_blog_id: int
    link_url_raw: str
    link_text: str | None


class AddLogRequest(BaseModel):
    blog_id: int | None = None
    stage: str
    result: str
    message: str


def build_persistence_state(settings: Settings | None = None) -> PersistenceState:
    """Construct the persistence service state."""
    resolved = settings or Settings.from_env()
    repository = build_repository(db_path=resolved.db_path, db_dsn=resolved.db_dsn)
    return PersistenceState(
        repository=repository,
        graph_service=GraphService(repository),
        stats_service=StatsService(repository),
    )


def create_app(state: PersistenceState | None = None) -> FastAPI:
    """Create the persistence API app."""
    app = FastAPI(title="HeyBlog Persistence Service", version="0.1.0")
    app.state.persistence_state = state or build_persistence_state()

    def get_state() -> PersistenceState:
        return app.state.persistence_state

    @app.get("/internal/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/internal/blogs")
    def list_blogs() -> list[dict[str, Any]]:
        return get_state().repository.list_blogs()

    @app.get("/internal/queue/next")
    def next_waiting(max_depth: int) -> dict[str, Any] | None:
        row = get_state().repository.get_next_waiting_blog(max_depth)
        return dict(row) if row else None

    @app.get("/internal/blogs/{blog_id}")
    def get_blog(blog_id: int) -> dict[str, Any] | None:
        return get_state().repository.get_blog(blog_id)

    @app.post("/internal/blogs/upsert")
    def upsert_blog(payload: UpsertBlogRequest) -> dict[str, Any]:
        blog_id, inserted = get_state().repository.upsert_blog(**payload.model_dump())
        return {"id": blog_id, "inserted": inserted}

    @app.post("/internal/blogs/{blog_id}/result")
    def mark_blog_result(blog_id: int, payload: BlogResultRequest) -> dict[str, bool]:
        get_state().repository.mark_blog_result(blog_id=blog_id, **payload.model_dump())
        return {"ok": True}

    @app.get("/internal/edges")
    def list_edges() -> list[dict[str, Any]]:
        return get_state().repository.list_edges()

    @app.post("/internal/edges")
    def add_edge(payload: AddEdgeRequest) -> dict[str, bool]:
        get_state().repository.add_edge(**payload.model_dump())
        return {"ok": True}

    @app.get("/internal/logs")
    def list_logs(limit: int = 100) -> list[dict[str, Any]]:
        return get_state().repository.list_logs(limit=limit)

    @app.post("/internal/logs")
    def add_log(payload: AddLogRequest) -> dict[str, bool]:
        get_state().repository.add_log(**payload.model_dump())
        return {"ok": True}

    @app.get("/internal/stats")
    def get_stats() -> dict[str, Any]:
        return get_state().stats_service.stats()

    @app.get("/internal/graph")
    def get_graph() -> dict[str, Any]:
        return get_state().graph_service.graph()

    @app.get("/internal/search-snapshot")
    def get_search_snapshot() -> dict[str, list[dict[str, Any]]]:
        repository = get_state().repository
        return {
            "blogs": repository.list_blogs(),
            "edges": repository.list_edges(),
            "logs": repository.list_logs(limit=500),
        }

    return app


app = create_app()
