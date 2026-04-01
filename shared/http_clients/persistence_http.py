"""HTTP client wrapper for the persistence service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx


class PersistenceHttpClient:
    """Expose repository-like methods backed by the persistence API."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 10.0,
        seed_path: Path | None = None,
        export_dir: Path | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.seed_path = seed_path
        self.export_dir = export_dir
        self.client = httpx.Client(base_url=self.base_url, timeout=timeout_seconds)

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        response = self.client.post(path, json=payload)
        response.raise_for_status()
        return response.json()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = self.client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    def add_log(
        self, stage: str, result: str, message: str, blog_id: int | None = None
    ) -> None:
        self._post(
            "/internal/logs",
            {
                "blog_id": blog_id,
                "stage": stage,
                "result": result,
                "message": message,
            },
        )

    def upsert_blog(
        self,
        *,
        url: str,
        normalized_url: str,
        domain: str,
        source_blog_id: int | None,
    ) -> tuple[int, bool]:
        payload = self._post(
            "/internal/blogs/upsert",
            {
                "url": url,
                "normalized_url": normalized_url,
                "domain": domain,
                "source_blog_id": source_blog_id,
            },
        )
        return int(payload["id"]), bool(payload["inserted"])

    def get_next_waiting_blog(self) -> dict[str, Any] | None:
        return self._get("/internal/queue/next")

    def mark_blog_result(
        self,
        *,
        blog_id: int,
        crawl_status: str,
        status_code: int | None,
        friend_links_count: int,
        metadata_captured: bool = False,
        title: str | None = None,
        icon_url: str | None = None,
    ) -> None:
        self._post(
            f"/internal/blogs/{blog_id}/result",
            {
                "crawl_status": crawl_status,
                "status_code": status_code,
                "friend_links_count": friend_links_count,
                "metadata_captured": metadata_captured,
                "title": title,
                "icon_url": icon_url,
            },
        )

    def add_edge(
        self,
        *,
        from_blog_id: int,
        to_blog_id: int,
        link_url_raw: str,
        link_text: str | None,
    ) -> None:
        self._post(
            "/internal/edges",
            {
                "from_blog_id": from_blog_id,
                "to_blog_id": to_blog_id,
                "link_url_raw": link_url_raw,
                "link_text": link_text,
            },
        )

    def list_blogs(self) -> list[dict[str, Any]]:
        return self._get("/internal/blogs")

    def list_blogs_catalog(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        site: str | None = None,
        url: str | None = None,
        status: str | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        return self._get(
            "/internal/blogs/catalog",
            {
                "page": page,
                "page_size": page_size,
                "site": site,
                "url": url,
                "status": status,
                "q": q,
            },
        )

    def get_blog(self, blog_id: int) -> dict[str, Any] | None:
        return self._get(f"/internal/blogs/{blog_id}")

    def get_blog_detail(self, blog_id: int) -> dict[str, Any]:
        return self._get(f"/internal/blogs/{blog_id}/detail")

    def list_edges(self) -> list[dict[str, Any]]:
        return self._get("/internal/edges")

    def list_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._get("/internal/logs", {"limit": limit})

    def stats(self) -> dict[str, Any]:
        return self._get("/internal/stats")

    def graph(self) -> dict[str, Any]:
        return self._get("/internal/graph")

    def graph_view(
        self,
        *,
        strategy: str = "degree",
        limit: int = 180,
        sample_mode: str = "off",
        sample_value: float | None = None,
        sample_seed: int = 7,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "strategy": strategy,
            "limit": limit,
            "sample_mode": sample_mode,
            "sample_seed": sample_seed,
        }
        if sample_value is not None:
            params["sample_value"] = sample_value
        return self._get("/internal/graph/views/core", params)

    def graph_neighbors(self, blog_id: int, *, hops: int = 1, limit: int = 120) -> dict[str, Any]:
        return self._get(
            f"/internal/graph/nodes/{blog_id}/neighbors",
            {"hops": hops, "limit": limit},
        )

    def latest_graph_snapshot(self) -> dict[str, Any]:
        return self._get("/internal/graph/snapshots/latest")

    def graph_snapshot(self, version: str) -> dict[str, Any]:
        return self._get(f"/internal/graph/snapshots/{version}")

    def search_snapshot(self) -> dict[str, list[dict[str, Any]]]:
        return self._get("/internal/search-snapshot")

    def reset(self) -> dict[str, Any]:
        response = self.client.post("/internal/database/reset")
        response.raise_for_status()
        return response.json()
