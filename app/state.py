"""Compose and hold long-lived application services."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.crawler.pipeline import CrawlPipeline
from app.db.repository import RepositoryProtocol
from app.db.repository import build_repository
from app.services.graph_service import GraphService
from app.services.stats_service import StatsService


@dataclass(slots=True)
class AppState:
    """Container for service instances shared across requests."""

    settings: Settings
    repository: RepositoryProtocol
    pipeline: CrawlPipeline
    graph_service: GraphService
    stats_service: StatsService


def build_app_state(settings: Settings | None = None) -> AppState:
    """Create default service wiring from provided or environment settings."""
    resolved = settings or Settings.from_env()
    repository = build_repository(db_path=resolved.db_path, db_dsn=resolved.db_dsn)
    pipeline = CrawlPipeline(resolved, repository)
    return AppState(
        settings=resolved,
        repository=repository,
        pipeline=pipeline,
        graph_service=GraphService(repository),
        stats_service=StatsService(repository),
    )
