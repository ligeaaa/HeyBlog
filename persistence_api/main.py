"""Persistence service exposing repository operations over HTTP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from persistence_api.repository import BLOG_CATALOG_DEFAULT_PAGE_SIZE
from persistence_api.repository import BLOG_LABELING_DEFAULT_PAGE_SIZE
from persistence_api.age_graph import AgeGraphManager
from persistence_api.repository import BlogLabelingConflictError
from persistence_api.repository import BlogLabelingNotFoundError
from persistence_api.graph_service import GraphService
from persistence_api.migrations import run_postgres_migrations
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
    email: str | None = None


class CreateIngestionRequest(BaseModel):
    homepage_url: str
    email: str


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


class ReplaceBlogLabelsRequest(BaseModel):
    tag_ids: list[int]


class CreateBlogLabelTagRequest(BaseModel):
    name: str


class FinalizeBlogDedupScanRunRequest(BaseModel):
    crawler_restart_attempted: bool
    crawler_restart_succeeded: bool
    search_reindexed: bool
    error_message: str | None = None


def build_persistence_state(settings: Settings | None = None) -> PersistenceState:
    """Construct the persistence service state."""
    resolved = settings or Settings.from_env()
    if resolved.db_dsn:
        run_postgres_migrations(resolved.db_dsn)
    repository = build_repository(db_path=resolved.db_path, db_dsn=resolved.db_dsn, settings=resolved)
    age_manager = AgeGraphManager(
        getattr(repository, "engine", None),
        enabled=resolved.age_enabled and resolved.age_shadow_reads,
        graph_name=resolved.age_graph_name,
    )
    return PersistenceState(
        repository=repository,
        # Keep graph/stats assembly owned by persistence so this service does not
        # depend on backend-only modules for its own read models.
        graph_service=GraphService(
            repository,
            resolved.export_dir,
            graph_backend=resolved.graph_backend,
            snapshot_namespace=resolved.graph_snapshot_namespace,
            age_manager=age_manager,
        ),
        stats_service=StatsService(repository),
    )


def create_app(state: PersistenceState | None = None) -> FastAPI:
    """Create the persistence API app."""
    app = FastAPI(title="HeyBlog Persistence Service", version="0.1.0")
    app.state.persistence_state = state

    def get_state() -> PersistenceState:
        if app.state.persistence_state is None:
            app.state.persistence_state = build_persistence_state()
        return app.state.persistence_state

    @app.get("/internal/health")
    def health() -> dict[str, Any]:
        return {"status": "ok"} | get_state().graph_service.graph_status()

    @app.get("/internal/blogs")
    def list_blogs() -> list[dict[str, Any]]:
        return get_state().repository.list_blogs()

    @app.get("/internal/blogs/catalog")
    def list_blogs_catalog(
        page: int = 1,
        page_size: int = BLOG_CATALOG_DEFAULT_PAGE_SIZE,
        site: str | None = None,
        url: str | None = None,
        status: str | None = None,
        statuses: str | None = None,
        q: str | None = None,
        sort: str = "id_desc",
        has_title: str | None = None,
        has_icon: str | None = None,
        min_connections: str | None = None,
    ) -> dict[str, Any]:
        try:
            return get_state().repository.list_blogs_catalog(
                page=page,
                page_size=page_size,
                site=site,
                url=url,
                status=status,
                statuses=statuses,
                q=q,
                sort=sort,
                has_title=has_title,
                has_icon=has_icon,
                min_connections=min_connections,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/internal/blogs/lookup")
    def lookup_blog_candidates(url: str) -> dict[str, Any]:
        try:
            return get_state().repository.lookup_blog_candidates(url=url)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/internal/ingestion-requests")
    def list_priority_ingestion_requests() -> list[dict[str, Any]]:
        return get_state().repository.list_priority_ingestion_requests()

    @app.get("/internal/blog-labeling/candidates")
    def list_blog_labeling_candidates(
        page: int = 1,
        page_size: int = BLOG_LABELING_DEFAULT_PAGE_SIZE,
        q: str | None = None,
        label: str | None = None,
        labeled: str | None = None,
        sort: str = "id_desc",
    ) -> dict[str, Any]:
        try:
            return get_state().repository.list_blog_labeling_candidates(
                page=page,
                page_size=page_size,
                q=q,
                label=label,
                labeled=labeled,
                sort=sort,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/internal/blog-labeling/tags")
    def list_blog_label_tags() -> list[dict[str, Any]]:
        return get_state().repository.list_blog_label_tags()

    @app.post("/internal/blog-labeling/tags")
    def create_blog_label_tag(payload: CreateBlogLabelTagRequest) -> dict[str, Any]:
        try:
            return get_state().repository.create_blog_label_tag(name=payload.name)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.put("/internal/blog-labeling/labels/{blog_id}")
    def replace_blog_labels(blog_id: int, payload: ReplaceBlogLabelsRequest) -> dict[str, Any]:
        try:
            return get_state().repository.replace_blog_link_labels(blog_id=blog_id, tag_ids=payload.tag_ids)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except BlogLabelingNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except BlogLabelingConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/internal/blog-labeling/export")
    def export_blog_label_training_csv() -> Response:
        return Response(
            content=get_state().repository.export_blog_label_training_csv(),
            media_type="text/csv",
            headers={
                "content-disposition": 'attachment; filename="blog-label-training-export.csv"',
            },
        )

    @app.get("/internal/queue/next")
    def next_waiting(include_priority: bool = True) -> dict[str, Any] | None:
        row = get_state().repository.get_next_waiting_blog(include_priority=include_priority)
        return dict(row) if row else None

    @app.get("/internal/queue/priority-next")
    def next_priority_waiting() -> dict[str, Any] | None:
        row = get_state().repository.get_next_priority_blog()
        return dict(row) if row else None

    @app.get("/internal/blogs/{blog_id}")
    def get_blog(blog_id: int) -> dict[str, Any] | None:
        return get_state().repository.get_blog(blog_id)

    @app.get("/internal/blogs/{blog_id}/detail")
    def get_blog_detail(blog_id: int) -> dict[str, Any]:
        payload = get_state().repository.get_blog_detail(blog_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="blog_not_found")
        return payload

    @app.post("/internal/ingestion-requests")
    def create_ingestion_request(payload: CreateIngestionRequest) -> dict[str, Any]:
        try:
            return get_state().repository.create_ingestion_request(**payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/internal/ingestion-requests/{request_id}")
    def get_ingestion_request(request_id: int, request_token: str) -> dict[str, Any]:
        payload = get_state().repository.get_ingestion_request(
            request_id=request_id,
            request_token=request_token,
        )
        if payload is None:
            raise HTTPException(status_code=404, detail="ingestion_request_not_found")
        return payload

    @app.post("/internal/blog-dedup-scans")
    def run_blog_dedup_scan(crawler_was_running: bool = False) -> dict[str, Any]:
        return get_state().repository.run_blog_dedup_scan(crawler_was_running=crawler_was_running)

    @app.post("/internal/blog-dedup-scans/runs")
    def create_blog_dedup_scan_run(crawler_was_running: bool = False) -> dict[str, Any]:
        return get_state().repository.create_blog_dedup_scan_run(crawler_was_running=crawler_was_running)

    @app.post("/internal/blog-dedup-scans/{run_id}/execute")
    def execute_blog_dedup_scan_run(run_id: int) -> dict[str, Any]:
        try:
            return get_state().repository.execute_blog_dedup_scan_run(run_id=run_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/internal/blog-dedup-scans/{run_id}/finalize")
    def finalize_blog_dedup_scan_run(run_id: int, payload: FinalizeBlogDedupScanRunRequest) -> dict[str, Any]:
        try:
            return get_state().repository.finalize_blog_dedup_scan_run(run_id=run_id, **payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/internal/blog-dedup-scans/latest")
    def get_latest_blog_dedup_scan_run() -> dict[str, Any]:
        payload = get_state().repository.get_latest_blog_dedup_scan_run()
        if payload is None:
            raise HTTPException(status_code=404, detail="blog_dedup_scan_run_not_found")
        return payload

    @app.get("/internal/blog-dedup-scans/{run_id}")
    def get_blog_dedup_scan_run(run_id: int) -> dict[str, Any]:
        payload = get_state().repository.get_blog_dedup_scan_run(run_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="blog_dedup_scan_run_not_found")
        return payload

    @app.get("/internal/blog-dedup-scans/{run_id}/items")
    def list_blog_dedup_scan_run_items(run_id: int) -> list[dict[str, Any]]:
        return get_state().repository.list_blog_dedup_scan_run_items(run_id)

    @app.post("/internal/ingestion-requests/by-blog/{blog_id}/crawling")
    def mark_ingestion_request_crawling(blog_id: int) -> dict[str, bool]:
        get_state().repository.mark_ingestion_request_crawling(blog_id=blog_id)
        return {"ok": True}

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

    @app.get("/internal/graph/status")
    def get_graph_status() -> dict[str, Any]:
        return get_state().graph_service.graph_status()

    @app.post("/internal/graph/shadow/rebuild")
    def rebuild_graph_shadow() -> dict[str, Any]:
        return get_state().graph_service.rebuild_shadow_graph()

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
            "logs": [],
        }

    @app.post("/internal/database/reset")
    def reset_database() -> dict[str, Any]:
        return get_state().repository.reset()

    return app


app = create_app()
