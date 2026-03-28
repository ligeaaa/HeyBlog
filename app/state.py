"""Compose and hold long-lived application services."""

from __future__ import annotations

from dataclasses import dataclass

from crawler.pipeline import CrawlPipeline
from backend.graph_service import GraphService
from backend.stats_service import StatsService
from persistence_api.repository import RepositoryProtocol
from persistence_api.repository import build_repository
from shared.config import Settings


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
