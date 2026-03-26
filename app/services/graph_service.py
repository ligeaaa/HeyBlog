from __future__ import annotations

from app.db.repository import Repository


class GraphService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def graph(self) -> dict:
        return {
            "nodes": self.repository.list_blogs(),
            "edges": self.repository.list_edges(),
        }
