"""Search service with a lightweight rebuildable index."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from shared.config import Settings
from shared.http_clients.persistence_http import PersistenceHttpClient


def _normalize(value: str) -> str:
    return value.casefold().strip()


@dataclass(slots=True)
class SearchService:
    """Manage a small rebuildable search index."""

    persistence: Any
    cache_path: Path

    def _read_cache(self) -> dict[str, list[dict[str, Any]]]:
        if self.cache_path.exists():
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        return {"blogs": [], "edges": [], "logs": []}

    def rebuild(self) -> dict[str, Any]:
        snapshot = self.persistence.search_snapshot()
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "blogs": len(snapshot["blogs"]),
            "edges": len(snapshot["edges"]),
            "logs": len(snapshot["logs"]),
            "cache_path": str(self.cache_path),
        }

    def search(self, query: str) -> dict[str, Any]:
        normalized = _normalize(query)
        if not normalized:
            return {"query": query, "blogs": [], "edges": [], "logs": []}

        snapshot = self._read_cache()
        if not any(snapshot.values()):
            snapshot = self.persistence.search_snapshot()

        def contains(text: str | None) -> bool:
            return bool(text) and normalized in text.casefold()

        blogs = [
            blog
            for blog in snapshot["blogs"]
            if contains(blog.get("domain"))
            or contains(blog.get("url"))
            or contains(blog.get("normalized_url"))
        ]
        edges = [
            edge
            for edge in snapshot["edges"]
            if contains(edge.get("link_url_raw")) or contains(edge.get("link_text"))
        ]
        logs = [log for log in snapshot["logs"] if contains(log.get("message"))]
        return {"query": query, "blogs": blogs, "edges": edges, "logs": logs}


def build_search_service(settings: Settings | None = None) -> SearchService:
    """Construct the search service."""
    resolved = settings or Settings.from_env()
    cache_dir = resolved.search_cache_dir or (Path.cwd() / "data" / "search-cache")
    return SearchService(
        persistence=PersistenceHttpClient(
            resolved.persistence_base_url,
            timeout_seconds=resolved.request_timeout_seconds,
        ),
        cache_path=cache_dir / "search-index.json",
    )


def create_app(service: SearchService | None = None) -> FastAPI:
    """Create the search service app."""
    app = FastAPI(title="HeyBlog Search Service", version="0.1.0")
    app.state.search_service = service or build_search_service()

    def get_service() -> SearchService:
        return app.state.search_service

    @app.get("/internal/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/internal/search")
    def search(q: str) -> dict[str, Any]:
        return get_service().search(q)

    @app.post("/internal/search/reindex")
    def reindex() -> dict[str, Any]:
        return get_service().rebuild()

    return app


app = create_app()
