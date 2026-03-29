"""Assemble graph payloads inside the persistence service boundary."""

from __future__ import annotations

from typing import Any

from persistence_api.repository import RepositoryProtocol


class GraphService:
    """Create combined node-edge graph views from repository data."""

    def __init__(self, repository: RepositoryProtocol) -> None:
        """Store repository dependency for graph reads."""
        self.repository = repository

    def graph(self) -> dict[str, Any]:
        """Return current graph with node and edge lists."""
        return {
            "nodes": self.repository.list_blogs(),
            "edges": self.repository.list_edges(),
        }
