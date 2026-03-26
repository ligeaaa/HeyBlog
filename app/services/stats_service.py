from __future__ import annotations

from app.db.repository import Repository


class StatsService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def status(self) -> dict:
        stats = self.repository.stats()
        return {
            "is_running": False,
            "pending_tasks": stats["pending_tasks"],
            "processing_tasks": stats["processing_tasks"],
            "finished_tasks": stats["finished_tasks"],
            "failed_tasks": stats["failed_tasks"],
            "total_blogs": stats["total_blogs"],
            "total_edges": stats["total_edges"],
        }

    def stats(self) -> dict:
        return self.repository.stats()
