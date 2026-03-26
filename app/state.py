from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.crawler.pipeline import CrawlPipeline
from app.db.repository import Repository
from app.services.graph_service import GraphService
from app.services.stats_service import StatsService


@dataclass(slots=True)
class AppState:
    settings: Settings
    repository: Repository
    pipeline: CrawlPipeline
    graph_service: GraphService
    stats_service: StatsService


def build_app_state(settings: Settings | None = None) -> AppState:
    resolved = settings or Settings.from_env()
    repository = Repository(resolved.db_path)
    pipeline = CrawlPipeline(resolved, repository)
    return AppState(
        settings=resolved,
        repository=repository,
        pipeline=pipeline,
        graph_service=GraphService(repository),
        stats_service=StatsService(repository),
    )
