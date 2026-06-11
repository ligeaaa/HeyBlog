"""Crawler service exposing crawl execution over HTTP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel

from crawler.crawling.pipeline import CrawlPipeline
from shared.config import Settings
from shared.http_clients.persistence_http import PersistenceHttpClient
from crawler.runtime import CrawlerRuntimeService
from shared.observability import RequestIdMiddleware
from shared.observability import configure_logging
from shared.observability import get_logger
from shared.observability import log_event


SERVICE_NAME = "crawler"
LOGGER = get_logger(__name__)


@dataclass(slots=True)
class CrawlerState:
    """Bundle the crawler service dependencies attached to the FastAPI app.

    Attributes:
        pipeline: One-shot crawl pipeline used by bootstrap and run endpoints.
        runtime: Long-lived runtime controller used by runtime endpoints.
    """

    pipeline: CrawlPipeline
    runtime: CrawlerRuntimeService


class RunBatchRequest(BaseModel):
    """Request body for the synchronous runtime batch endpoint.

    Attributes:
        max_nodes: Maximum number of blogs the runtime batch should process.
    """

    max_nodes: int


def build_crawler_state(settings: Settings | None = None) -> CrawlerState:
    """Build the crawler service state and its HTTP-backed dependencies.

    Args:
        settings: Optional settings override. When omitted, environment-derived
            settings are loaded.

    Returns:
        A fully initialized ``CrawlerState`` containing the pipeline and runtime
        service.
    """
    resolved = settings or Settings.from_env()
    # The crawler process talks to persistence over HTTP so the service can run
    # standalone without importing repository internals into the web layer.
    repository = PersistenceHttpClient(
        resolved.persistence_base_url,
        timeout_seconds=resolved.request_timeout_seconds,
        seed_path=resolved.seed_path,
        export_dir=resolved.export_dir,
    )
    pipeline = CrawlPipeline(resolved, repository)
    return CrawlerState(
        pipeline=pipeline,
        runtime=CrawlerRuntimeService(
            pipeline,
            worker_count=resolved.runtime_worker_count,
            auto_start_interval_seconds=resolved.runtime_auto_start_interval_seconds,
        ),
    )


def create_app(state: CrawlerState | None = None) -> FastAPI:
    """Create the FastAPI crawler service application.

    Args:
        state: Optional prebuilt crawler state used mainly by tests.

    Returns:
        A configured ``FastAPI`` application exposing crawler control routes.
    """
    settings = Settings.from_env()
    configure_logging(
        service=SERVICE_NAME,
        log_dir=settings.log_dir,
        level=settings.log_level,
        file_enabled=settings.log_file_enabled,
        console_enabled=settings.log_console_enabled,
        log_format=settings.log_format,
        retention_days=settings.log_retention_days,
    )
    app = FastAPI(title="HeyBlog Crawler Service", version="0.1.0")
    app.add_middleware(RequestIdMiddleware, service=SERVICE_NAME)
    app.state.crawler_state = state or build_crawler_state()

    @app.on_event("startup")
    def start_runtime_auto_scheduler() -> None:
        """Start runtime auto scheduling when the ASGI app starts serving."""
        scheduler_result = app.state.crawler_state.runtime.start_auto_scheduler()
        log_event(
            LOGGER,
            event="crawler.runtime.auto_scheduler.started",
            message="crawler runtime auto scheduler started",
            stage="runtime",
            accepted=scheduler_result.get("accepted"),
            interval_seconds=scheduler_result.get("interval_seconds"),
            reason=scheduler_result.get("reason"),
        )

    @app.on_event("shutdown")
    def stop_runtime_auto_scheduler() -> None:
        """Stop runtime auto scheduling when the ASGI app shuts down."""
        scheduler_result = app.state.crawler_state.runtime.stop_auto_scheduler()
        log_event(
            LOGGER,
            event="crawler.runtime.auto_scheduler.stopped",
            message="crawler runtime auto scheduler stopped",
            stage="runtime",
            accepted=scheduler_result.get("accepted"),
        )

    def get_state() -> CrawlerState:
        """Return the app-scoped crawler state container.

        Returns:
            The ``CrawlerState`` stored on the FastAPI application object.
        """
        return app.state.crawler_state

    @app.get("/internal/health")
    def health() -> dict[str, str]:
        """Return a basic liveness payload for service health checks.

        Returns:
            A static ``{"status": "ok"}`` response.
        """
        return {"status": "ok"}

    @app.post("/internal/crawl/bootstrap")
    def bootstrap() -> dict[str, Any]:
        """Trigger seed bootstrap using the configured pipeline.

        Returns:
            Bootstrap result payload describing the imported seed file and
            created row count.
        """
        result = get_state().pipeline.bootstrap_seeds()
        log_event(
            LOGGER,
            event="crawl.bootstrap.request_completed",
            message="crawl bootstrap request completed",
            stage="bootstrap",
            imported=result.get("imported"),
            seed_path=result.get("seed_path"),
        )
        return result

    @app.post("/internal/crawl/run")
    def run_crawl(max_nodes: int | None = None) -> dict[str, Any]:
        """Run one synchronous crawl batch through the pipeline.

        Args:
            max_nodes: Optional override for the number of blogs to process.

        Returns:
            Batch crawl result payload from ``CrawlPipeline.run_once``.
        """
        # This is the direct one-shot entrypoint for CrawlPipeline.run_once().
        capacity = get_state().pipeline.capacity_gate.check()
        if not capacity.allowed:
            raise HTTPException(
                status_code=409,
                detail={
                    "reason": capacity.reason,
                    "raw_count": capacity.raw_count,
                    "limit": capacity.limit,
                },
            )
        result = get_state().pipeline.run_once(max_nodes=max_nodes)
        log_event(
            LOGGER,
            event="crawl.batch.completed",
            message="crawl batch completed",
            stage="crawl",
            processed=result.get("processed"),
            discovered=result.get("discovered"),
            failed=result.get("failed"),
            max_nodes=max_nodes,
        )
        return result

    @app.get("/internal/runtime/status")
    def runtime_status() -> dict[str, Any]:
        """Return the full runtime status snapshot.

        Returns:
            Serialized runtime snapshot for all workers and aggregate state.
        """
        return get_state().runtime.status()

    @app.get("/internal/runtime/current")
    def runtime_current() -> dict[str, Any]:
        """Return the compatibility-focused current runtime view.

        Returns:
            Runtime payload centered on one representative active worker.
        """
        return get_state().runtime.current()

    @app.post("/internal/runtime/start")
    def runtime_start() -> dict[str, Any]:
        """Start the background crawler runtime loop.

        Returns:
            Updated runtime snapshot after the start request is processed.
        """
        result = get_state().runtime.start()
        if result.get("accepted") is False and result.get("reason") == "raw_discovered_url_limit_reached":
            capacity = result.get("capacity", {})
            raise HTTPException(
                status_code=409,
                detail={
                    "reason": result.get("reason"),
                    "raw_count": capacity.get("raw_count"),
                    "limit": capacity.get("limit"),
                },
            )
        log_event(
            LOGGER,
            event="crawler.runtime.started",
            message="crawler runtime start requested",
            stage="runtime",
            runner_status=result.get("runner_status"),
        )
        return result

    @app.post("/internal/runtime/stop")
    def runtime_stop() -> dict[str, Any]:
        """Request the background crawler runtime loop to stop.

        Returns:
            Updated runtime snapshot after the stop request is processed.
        """
        result = get_state().runtime.stop()
        log_event(
            LOGGER,
            event="crawler.runtime.stopped",
            message="crawler runtime stop requested",
            stage="runtime",
            runner_status=result.get("runner_status"),
        )
        return result

    @app.post("/internal/runtime/run-batch")
    def runtime_run_batch(payload: RunBatchRequest) -> dict[str, Any]:
        """Run one synchronous runtime batch through the worker-pool layer.

        Args:
            payload: Request body containing the max-node batch limit.

        Returns:
            Runtime batch result payload including acceptance state and runtime
            snapshot data.
        """
        # Runtime batching uses the same pipeline, but with worker-pool state
        # tracking layered on top for long-lived service execution.
        result = get_state().runtime.run_batch(payload.max_nodes)
        if result.get("accepted") is False and result.get("reason") == "raw_discovered_url_limit_reached":
            capacity = result.get("capacity", {})
            raise HTTPException(
                status_code=409,
                detail={
                    "reason": result.get("reason"),
                    "raw_count": capacity.get("raw_count"),
                    "limit": capacity.get("limit"),
                },
            )
        log_event(
            LOGGER,
            event="crawler.runtime.batch_completed",
            message="crawler runtime batch completed",
            stage="runtime",
            max_nodes=payload.max_nodes,
            accepted=result.get("accepted"),
            mode=result.get("mode"),
        )
        return result

    return app


app = create_app()
