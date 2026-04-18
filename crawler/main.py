"""Crawler service exposing crawl execution over HTTP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from crawler.crawling.pipeline import CrawlPipeline
from shared.config import Settings
from shared.http_clients.persistence_http import PersistenceHttpClient
from crawler.runtime import CrawlerRuntimeService


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
            priority_seed_normal_queue_slots=resolved.priority_seed_normal_queue_slots,
        ),
    )


def create_app(state: CrawlerState | None = None) -> FastAPI:
    """Create the FastAPI crawler service application.

    Args:
        state: Optional prebuilt crawler state used mainly by tests.

    Returns:
        A configured ``FastAPI`` application exposing crawler control routes.
    """
    app = FastAPI(title="HeyBlog Crawler Service", version="0.1.0")
    app.state.crawler_state = state or build_crawler_state()

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
        return get_state().pipeline.bootstrap_seeds()

    @app.post("/internal/crawl/run")
    def run_crawl(max_nodes: int | None = None) -> dict[str, Any]:
        """Run one synchronous crawl batch through the pipeline.

        Args:
            max_nodes: Optional override for the number of blogs to process.

        Returns:
            Batch crawl result payload from ``CrawlPipeline.run_once``.
        """
        # This is the direct one-shot entrypoint for CrawlPipeline.run_once().
        return get_state().pipeline.run_once(max_nodes=max_nodes)

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
        return get_state().runtime.start()

    @app.post("/internal/runtime/stop")
    def runtime_stop() -> dict[str, Any]:
        """Request the background crawler runtime loop to stop.

        Returns:
            Updated runtime snapshot after the stop request is processed.
        """
        return get_state().runtime.stop()

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
        return get_state().runtime.run_batch(payload.max_nodes)

    return app


app = create_app()
