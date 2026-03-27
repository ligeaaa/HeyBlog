"""Crawler service exposing crawl execution over HTTP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI

from app.clients.persistence_http import PersistenceHttpClient
from app.config import Settings
from app.crawler.pipeline import CrawlPipeline


@dataclass(slots=True)
class CrawlerState:
    """State container for the crawler service."""

    pipeline: CrawlPipeline


def build_crawler_state(settings: Settings | None = None) -> CrawlerState:
    """Build the crawler service state."""
    resolved = settings or Settings.from_env()
    repository = PersistenceHttpClient(
        resolved.persistence_base_url,
        timeout_seconds=resolved.request_timeout_seconds,
        seed_path=resolved.seed_path,
        export_dir=resolved.export_dir,
    )
    return CrawlerState(pipeline=CrawlPipeline(resolved, repository))


def create_app(state: CrawlerState | None = None) -> FastAPI:
    """Create the crawler service app."""
    app = FastAPI(title="HeyBlog Crawler Service", version="0.1.0")
    app.state.crawler_state = state or build_crawler_state()

    def get_state() -> CrawlerState:
        return app.state.crawler_state

    @app.get("/internal/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/internal/crawl/bootstrap")
    def bootstrap() -> dict[str, Any]:
        return get_state().pipeline.bootstrap_seeds()

    @app.post("/internal/crawl/run")
    def run_crawl(max_nodes: int | None = None) -> dict[str, Any]:
        return get_state().pipeline.run_once(max_nodes=max_nodes)

    return app


app = create_app()

