"""Public backend service that aggregates internal services."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Thread
from time import sleep
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import Response
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
    maintenance_in_progress: bool = False
    admin_token: str | None = None
    admin_dev_bypass: bool = False


class RunBatchRequest(BaseModel):
    max_nodes: int


class CreateIngestionRequest(BaseModel):
    homepage_url: str
    email: str


class ReplaceBlogLabelsRequest(BaseModel):
    tag_ids: list[int]


class CreateBlogLabelTagRequest(BaseModel):
    name: str


def _raise_for_maintenance(state: BackendState) -> None:
    if state.maintenance_in_progress:
        raise HTTPException(status_code=409, detail="maintenance_in_progress")


def _upstream_error_detail(exc: httpx.HTTPStatusError, default: Any = "upstream_error") -> Any:
    """Extract a stable detail payload from an upstream HTTP failure."""
    try:
        return exc.response.json().get("detail", default)
    except Exception:  # noqa: BLE001
        return default


def _raise_upstream_http_error(
    exc: httpx.HTTPStatusError,
    *,
    default: Any = "upstream_error",
    detail_override: Any | None = None,
) -> None:
    """Re-raise an upstream HTTP failure with FastAPI-compatible semantics."""
    detail = detail_override if detail_override is not None else _upstream_error_detail(exc, default)
    raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc


def _mark_url_refilter_run_failed(
    state: BackendState,
    *,
    run_id: int | None,
    error_message: str,
) -> None:
    """Best-effort persistence of a failed URL refilter run."""
    if run_id is None:
        return
    try:
        state.persistence.mark_url_refilter_run_failed(run_id=run_id, error_message=error_message)
    except Exception:  # noqa: BLE001
        pass


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
        admin_token=resolved.admin_token,
        admin_dev_bypass=resolved.admin_dev_bypass,
    )


def _execute_blog_dedup_scan_in_background(
    state: BackendState,
    *,
    run_id: int,
    crawler_was_running: bool,
) -> None:
    restart_attempted = False
    restart_succeeded = False
    search_reindexed = False
    error_message: str | None = None
    try:
        state.persistence.execute_blog_dedup_scan_run(run_id=run_id)
        try:
            state.search.reindex()
            search_reindexed = True
        except Exception:  # noqa: BLE001
            search_reindexed = False
    except httpx.HTTPStatusError as exc:
        error_message = str(_upstream_error_detail(exc))
    except Exception as exc:  # noqa: BLE001
        error_message = str(exc)
    finally:
        if crawler_was_running:
            restart_attempted = True
            try:
                state.crawler.start()
                restart_succeeded = True
            except Exception:  # noqa: BLE001
                restart_succeeded = False
        try:
            state.persistence.finalize_blog_dedup_scan_run(
                run_id=run_id,
                crawler_restart_attempted=restart_attempted,
                crawler_restart_succeeded=restart_succeeded,
                search_reindexed=search_reindexed,
                error_message=error_message,
            )
        except Exception:  # noqa: BLE001
            pass
        state.maintenance_in_progress = False


def _execute_url_refilter_in_background(
    state: BackendState,
    *,
    run_id: int,
) -> None:
    try:
        state.persistence.execute_url_refilter_run(run_id=run_id)
    except httpx.HTTPStatusError as exc:
        _mark_url_refilter_run_failed(state, run_id=run_id, error_message=str(_upstream_error_detail(exc)))
    except Exception as exc:  # noqa: BLE001
        _mark_url_refilter_run_failed(state, run_id=run_id, error_message=str(exc))
    finally:
        state.maintenance_in_progress = False


def create_app(state: BackendState | None = None) -> FastAPI:
    """Create the public backend app."""
    app = FastAPI(title="HeyBlog Backend Service", version="0.1.0")
    app.state.backend_state = state or build_backend_state()

    def get_state() -> BackendState:
        return app.state.backend_state

    def require_admin_access(request: Request) -> None:
        state = get_state()
        if state.admin_dev_bypass:
            return
        if not state.admin_token:
            raise HTTPException(status_code=503, detail="admin_auth_not_configured")
        authorization = request.headers.get("authorization", "").strip()
        if not authorization:
            raise HTTPException(status_code=401, detail="admin_auth_required")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="admin_auth_required")
        if token != state.admin_token:
            raise HTTPException(status_code=403, detail="admin_auth_invalid")

    def ensure_runtime_idle(*, retries: int = 20, delay_seconds: float = 0.1) -> dict[str, Any]:
        last_runtime = get_state().crawler.runtime_status()
        for _ in range(retries):
            if last_runtime.get("runner_status") == "idle":
                return last_runtime
            sleep(delay_seconds)
            last_runtime = get_state().crawler.runtime_status()
        raise HTTPException(status_code=409, detail="crawler_stop_timeout")

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

    @app.get("/api/blogs/catalog")
    def get_blogs_catalog(
        page: int = 1,
        page_size: int = 50,
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
            return get_state().persistence.list_blogs_catalog(
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
        except httpx.HTTPStatusError as exc:
            _raise_upstream_http_error(exc)

    @app.get("/api/blogs/lookup")
    def lookup_blog_candidates(url: str) -> dict[str, Any]:
        try:
            return get_state().persistence.lookup_blog_candidates(url=url)
        except httpx.HTTPStatusError as exc:
            _raise_upstream_http_error(exc)

    @app.get("/api/admin/blog-labeling/candidates")
    def get_blog_labeling_candidates(
        page: int = 1,
        page_size: int = 50,
        q: str | None = None,
        label: str | None = None,
        labeled: str | None = None,
        sort: str = "id_desc",
        _: None = Depends(require_admin_access),
    ) -> dict[str, Any]:
        try:
            return get_state().persistence.list_blog_labeling_candidates(
                page=page,
                page_size=page_size,
                q=q,
                label=label,
                labeled=labeled,
                sort=sort,
            )
        except httpx.HTTPStatusError as exc:
            _raise_upstream_http_error(exc)

    @app.get("/api/admin/blog-labeling/tags")
    def get_blog_label_tags(_: None = Depends(require_admin_access)) -> list[dict[str, Any]]:
        try:
            return get_state().persistence.list_blog_label_tags()
        except httpx.HTTPStatusError as exc:
            _raise_upstream_http_error(exc)

    @app.post("/api/admin/blog-labeling/tags")
    def post_blog_label_tag(
        payload: CreateBlogLabelTagRequest,
        _: None = Depends(require_admin_access),
    ) -> dict[str, Any]:
        try:
            return get_state().persistence.create_blog_label_tag(name=payload.name)
        except httpx.HTTPStatusError as exc:
            _raise_upstream_http_error(exc)

    @app.put("/api/admin/blog-labeling/labels/{blog_id}")
    def put_blog_labels(
        blog_id: int,
        payload: ReplaceBlogLabelsRequest,
        _: None = Depends(require_admin_access),
    ) -> dict[str, Any]:
        try:
            return get_state().persistence.replace_blog_link_labels(blog_id=blog_id, tag_ids=payload.tag_ids)
        except httpx.HTTPStatusError as exc:
            _raise_upstream_http_error(exc)

    @app.get("/api/admin/blog-labeling/export")
    def export_blog_label_training_csv(_: None = Depends(require_admin_access)) -> Response:
        try:
            csv_payload = get_state().persistence.export_blog_label_training_csv()
        except httpx.HTTPStatusError as exc:
            _raise_upstream_http_error(exc)
        return Response(
            content=csv_payload,
            media_type="text/csv",
            headers={
                "content-disposition": 'attachment; filename="blog-label-training-export.csv"',
            },
        )

    @app.get("/api/blogs/{blog_id}")
    def get_blog(blog_id: int) -> dict[str, Any]:
        try:
            blog = get_state().persistence.get_blog_detail(blog_id)
        except httpx.HTTPStatusError as exc:
            detail_override = "Blog not found" if exc.response.status_code == 404 else None
            _raise_upstream_http_error(exc, detail_override=detail_override)
        if blog is None:
            raise HTTPException(status_code=404, detail="Blog not found")
        return blog

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
        try:
            return get_state().persistence.graph_neighbors(blog_id, hops=hops, limit=limit)
        except httpx.HTTPStatusError as exc:
            _raise_upstream_http_error(exc)

    @app.get("/api/graph/snapshots/latest")
    def get_latest_graph_snapshot() -> dict[str, Any]:
        return get_state().persistence.latest_graph_snapshot()

    @app.get("/api/graph/snapshots/{version}")
    def get_graph_snapshot(version: str) -> dict[str, Any]:
        return get_state().persistence.graph_snapshot(version)

    @app.get("/api/stats")
    def get_stats() -> dict[str, Any]:
        return get_state().persistence.stats()

    @app.get("/api/filter-stats")
    def get_filter_stats() -> dict[str, Any]:
        try:
            return get_state().persistence.get_filter_stats_by_chain_order()
        except httpx.HTTPStatusError as exc:
            _raise_upstream_http_error(exc)

    @app.post("/api/admin/crawl/bootstrap")
    def bootstrap(_: None = Depends(require_admin_access)) -> dict[str, Any]:
        return get_state().crawler.bootstrap()

    @app.post("/api/admin/crawl/run")
    def run_crawl(max_nodes: int | None = None, _: None = Depends(require_admin_access)) -> dict[str, Any]:
        result = get_state().crawler.run(max_nodes=max_nodes)
        try:
            get_state().search.reindex()
        except Exception:  # noqa: BLE001
            pass
        return result

    @app.post("/api/ingestion-requests")
    def create_ingestion_request(payload: CreateIngestionRequest) -> dict[str, Any]:
        try:
            return get_state().persistence.create_ingestion_request(**payload.model_dump())
        except httpx.HTTPStatusError as exc:
            _raise_upstream_http_error(exc)

    @app.get("/api/ingestion-requests")
    def list_priority_ingestion_requests() -> list[dict[str, Any]]:
        try:
            return get_state().persistence.list_priority_ingestion_requests()
        except httpx.HTTPStatusError as exc:
            _raise_upstream_http_error(exc)

    @app.get("/api/ingestion-requests/{request_id}")
    def get_ingestion_request(request_id: int, request_token: str) -> dict[str, Any]:
        try:
            return get_state().persistence.get_ingestion_request(
                request_id=request_id,
                request_token=request_token,
            )
        except httpx.HTTPStatusError as exc:
            _raise_upstream_http_error(exc)

    @app.post("/api/admin/blog-dedup-scans")
    def run_blog_dedup_scan(_: None = Depends(require_admin_access)) -> dict[str, Any]:
        state = get_state()
        if state.maintenance_in_progress:
            raise HTTPException(status_code=409, detail="maintenance_in_progress")

        runtime_before = state.crawler.runtime_status()
        crawler_was_running = runtime_before.get("runner_status") in {"starting", "running", "stopping"}
        state.maintenance_in_progress = True
        try:
            if crawler_was_running:
                state.crawler.stop()
                ensure_runtime_idle()
            payload = state.persistence.create_blog_dedup_scan_run(crawler_was_running=crawler_was_running)
        except httpx.HTTPStatusError as exc:
            state.maintenance_in_progress = False
            _raise_upstream_http_error(exc)
        except HTTPException:
            state.maintenance_in_progress = False
            raise
        except Exception as exc:  # noqa: BLE001
            state.maintenance_in_progress = False
            raise HTTPException(status_code=500, detail="blog_dedup_scan_failed") from exc
        Thread(
            target=_execute_blog_dedup_scan_in_background,
            kwargs={
                "state": state,
                "run_id": int(payload["id"]),
                "crawler_was_running": crawler_was_running,
            },
            daemon=True,
        ).start()
        return payload

    @app.post("/api/admin/url-refilter-runs")
    def run_url_refilter(_: None = Depends(require_admin_access)) -> dict[str, Any]:
        state = get_state()
        if state.maintenance_in_progress:
            raise HTTPException(status_code=409, detail="maintenance_in_progress")

        runtime_before = state.crawler.runtime_status()
        crawler_was_running = runtime_before.get("runner_status") in {"starting", "running", "stopping"}
        state.maintenance_in_progress = True
        run_id: int | None = None
        try:
            payload = state.persistence.create_url_refilter_run(crawler_was_running=crawler_was_running)
            run_id = int(payload["id"])
            state.persistence.append_url_refilter_run_event(run_id=run_id, message="停止爬虫中")
            if crawler_was_running:
                state.crawler.stop()
                ensure_runtime_idle()
                state.persistence.append_url_refilter_run_event(run_id=run_id, message="爬虫已停止")
            else:
                state.persistence.append_url_refilter_run_event(run_id=run_id, message="爬虫已处于停止状态")
        except httpx.HTTPStatusError as exc:
            detail = _upstream_error_detail(exc)
            _mark_url_refilter_run_failed(state, run_id=run_id, error_message=str(detail))
            state.maintenance_in_progress = False
            _raise_upstream_http_error(exc, detail_override=detail)
        except HTTPException as exc:
            _mark_url_refilter_run_failed(state, run_id=run_id, error_message=str(exc.detail))
            state.maintenance_in_progress = False
            raise
        except Exception as exc:  # noqa: BLE001
            _mark_url_refilter_run_failed(state, run_id=run_id, error_message=str(exc))
            state.maintenance_in_progress = False
            raise HTTPException(status_code=500, detail="url_refilter_run_failed") from exc

        Thread(
            target=_execute_url_refilter_in_background,
            kwargs={
                "state": state,
                "run_id": run_id,
            },
            daemon=True,
        ).start()
        return payload

    @app.get("/api/admin/url-refilter-runs/latest")
    def get_latest_url_refilter_run(_: None = Depends(require_admin_access)) -> dict[str, Any]:
        try:
            return get_state().persistence.latest_url_refilter_run()
        except httpx.HTTPStatusError as exc:
            _raise_upstream_http_error(exc)

    @app.get("/api/admin/url-refilter-runs/{run_id}/events")
    def get_url_refilter_run_events(
        run_id: int,
        _: None = Depends(require_admin_access),
    ) -> list[dict[str, Any]]:
        try:
            return get_state().persistence.list_url_refilter_run_events(run_id)
        except httpx.HTTPStatusError as exc:
            _raise_upstream_http_error(exc)

    @app.get("/api/admin/blog-dedup-scans/latest")
    def get_latest_blog_dedup_scan_run(_: None = Depends(require_admin_access)) -> dict[str, Any]:
        try:
            return get_state().persistence.latest_blog_dedup_scan_run()
        except httpx.HTTPStatusError as exc:
            _raise_upstream_http_error(exc)

    @app.get("/api/admin/blog-dedup-scans/{run_id}/items")
    def get_blog_dedup_scan_run_items(
        run_id: int,
        _: None = Depends(require_admin_access),
    ) -> list[dict[str, Any]]:
        try:
            return get_state().persistence.list_blog_dedup_scan_run_items(run_id)
        except httpx.HTTPStatusError as exc:
            _raise_upstream_http_error(exc)

    @app.get("/api/admin/runtime/status")
    def runtime_status(_: None = Depends(require_admin_access)) -> dict[str, Any]:
        payload = get_state().crawler.runtime_status()
        payload["maintenance_in_progress"] = bool(get_state().maintenance_in_progress)
        return payload

    @app.get("/api/admin/runtime/current")
    def runtime_current(_: None = Depends(require_admin_access)) -> dict[str, Any]:
        return get_state().crawler.current()

    @app.post("/api/admin/runtime/start")
    def runtime_start(_: None = Depends(require_admin_access)) -> dict[str, Any]:
        _raise_for_maintenance(get_state())
        return get_state().crawler.start()

    @app.post("/api/admin/runtime/stop")
    def runtime_stop(_: None = Depends(require_admin_access)) -> dict[str, Any]:
        return get_state().crawler.stop()

    @app.post("/api/admin/runtime/run-batch")
    def runtime_run_batch(
        payload: RunBatchRequest,
        _: None = Depends(require_admin_access),
    ) -> dict[str, Any]:
        _raise_for_maintenance(get_state())
        result = get_state().crawler.run_batch(payload.max_nodes)
        try:
            get_state().search.reindex()
        except Exception:  # noqa: BLE001
            pass
        return result

    @app.post("/api/admin/database/reset")
    def reset_database(_: None = Depends(require_admin_access)) -> dict[str, Any]:
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
