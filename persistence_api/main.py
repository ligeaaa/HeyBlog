"""Persistence service exposing repository operations over HTTP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel

from persistence_api.graph_service import GraphService
from persistence_api.repository import RepositoryProtocol
from persistence_api.repository import build_repository
from persistence_api.stats_service import StatsService
from shared.config import Settings


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
    source_blog_id: int | None


class BlogResultRequest(BaseModel):
    crawl_status: str
    status_code: int | None
    friend_links_count: int
    metadata_captured: bool = False
    title: str | None = None
    icon_url: str | None = None


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
        # Keep graph/stats assembly owned by persistence so this service does not
        # depend on backend-only modules for its own read models.
        graph_service=GraphService(repository, resolved.export_dir),
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
    def next_waiting() -> dict[str, Any] | None:
        row = get_state().repository.get_next_waiting_blog()
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

    @app.get("/internal/graph/views/core")
    def get_graph_view(
        strategy: str = "degree",
        limit: int = 180,
        sample_mode: str = "off",
        sample_value: float | None = None,
        sample_seed: int = 7,
    ) -> dict[str, Any]:
        return get_state().graph_service.graph_view(
            strategy=strategy,
            limit=limit,
            sample_mode=sample_mode,
            sample_value=sample_value,
            sample_seed=sample_seed,
        )

    @app.get("/internal/graph/nodes/{blog_id}/neighbors")
    def get_graph_neighbors(blog_id: int, hops: int = 1, limit: int = 120) -> dict[str, Any]:
        try:
            return get_state().graph_service.graph_neighbors(node_id=blog_id, hops=hops, limit=limit)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="graph_node_not_found") from exc

    @app.get("/internal/graph/snapshots/latest")
    def get_latest_graph_snapshot() -> dict[str, Any]:
        return get_state().graph_service.latest_snapshot_manifest()

    @app.get("/internal/graph/snapshots/{version}")
    def get_graph_snapshot(version: str) -> dict[str, Any]:
        payload = get_state().graph_service.snapshot(version)
        if payload is None:
            raise HTTPException(status_code=404, detail="graph_snapshot_not_found")
        return payload

    @app.get("/internal/search-snapshot")
    def get_search_snapshot() -> dict[str, list[dict[str, Any]]]:
        repository = get_state().repository
        return {
            "blogs": repository.list_blogs(),
            "edges": repository.list_edges(),
            "logs": repository.list_logs(limit=500),
        }

    @app.post("/internal/database/reset")
    def reset_database() -> dict[str, Any]:
        return get_state().repository.reset()

    return app


app = create_app()
