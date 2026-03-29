"""Build stats payloads inside the persistence service boundary."""

from __future__ import annotations

from typing import Any

from persistence_api.repository import RepositoryProtocol


class StatsService:
    """Provide lightweight status and stats dictionaries for API handlers."""

    def __init__(self, repository: RepositoryProtocol) -> None:
        """Create service with repository dependency."""
        self.repository = repository

    def status(self) -> dict[str, Any]:
        """Return status counters expected by the legacy operator panel."""
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

    def stats(self) -> dict[str, Any]:
        """Return full repository statistics payload."""
        return self.repository.stats()
