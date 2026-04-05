"""Search service with a lightweight rebuildable index."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi import HTTPException

from shared.config import Settings
from shared.http_clients.persistence_http import PersistenceHttpClient


def _normalize(value: str) -> str:
    return value.casefold().strip()


def _normalize_kind(value: str) -> str:
    normalized = value.casefold().strip() or "all"
    if normalized not in {"all", "blogs", "relations"}:
        raise ValueError(f"Unsupported search kind: {value}")
    return normalized


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
            "logs": 0,
            "cache_path": str(self.cache_path),
        }

    def search(self, query: str, *, kind: str = "all", limit: int = 10) -> dict[str, Any]:
        normalized = _normalize(query)
        normalized_kind = _normalize_kind(kind)
        normalized_limit = max(1, min(limit, 50))
        if not normalized:
            return {
                "query": query,
                "kind": normalized_kind,
                "limit": normalized_limit,
                "blogs": [],
                "edges": [],
                "logs": [],
            }

        snapshot = self._read_cache()
        if not any(snapshot.values()):
            snapshot = self.persistence.search_snapshot()

        blog_map = {
            int(blog["id"]): {
                "id": int(blog["id"]),
                "domain": blog.get("domain"),
                "title": blog.get("title"),
                "icon_url": blog.get("icon_url"),
            }
            for blog in snapshot["blogs"]
            if blog.get("id") is not None
        }

        def contains(text: str | None) -> bool:
            return bool(text) and normalized in text.casefold()

        blogs: list[dict[str, Any]] = []
        if normalized_kind in {"all", "blogs"}:
            blogs = [
                blog
                for blog in snapshot["blogs"]
                if contains(blog.get("title"))
                or contains(blog.get("domain"))
                or contains(blog.get("url"))
                or contains(blog.get("normalized_url"))
            ][:normalized_limit]

        edges: list[dict[str, Any]] = []
        if normalized_kind in {"all", "relations"}:
            for edge in snapshot["edges"]:
                from_blog = blog_map.get(int(edge["from_blog_id"])) if edge.get("from_blog_id") else None
                to_blog = blog_map.get(int(edge["to_blog_id"])) if edge.get("to_blog_id") else None
                if not (
                    contains(edge.get("link_url_raw"))
                    or contains(edge.get("link_text"))
                    or contains(from_blog.get("domain") if from_blog else None)
                    or contains(from_blog.get("title") if from_blog else None)
                    or contains(to_blog.get("domain") if to_blog else None)
                    or contains(to_blog.get("title") if to_blog else None)
                ):
                    continue
                edges.append(
                    {
                        **edge,
                        "from_blog": from_blog,
                        "to_blog": to_blog,
                    }
                )
                if len(edges) >= normalized_limit:
                    break

        return {
            "query": query,
            "kind": normalized_kind,
            "limit": normalized_limit,
            "blogs": blogs,
            "edges": edges,
            "logs": [],
        }


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
    def search(q: str, kind: str = "all", limit: int = 10) -> dict[str, Any]:
        try:
            return get_service().search(q, kind=kind, limit=limit)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/internal/search/reindex")
    def reindex() -> dict[str, Any]:
        return get_service().rebuild()

    return app


app = create_app()
