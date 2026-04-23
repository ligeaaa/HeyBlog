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

    def _put(self, path: str, payload: dict[str, Any]) -> Any:
        response = self.client.put(path, json=payload)
        response.raise_for_status()
        return response.json()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = self.client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    def _get_text(self, path: str, params: dict[str, Any] | None = None) -> str:
        response = self.client.get(path, params=params)
        response.raise_for_status()
        return response.text

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
        email: str | None = None,
    ) -> tuple[int, bool]:
        payload = self._post(
            "/internal/blogs/upsert",
            {
                "url": url,
                "normalized_url": normalized_url,
                "domain": domain,
                "email": email,
            },
        )
        return int(payload["id"]), bool(payload["inserted"])

    def create_ingestion_request(self, *, homepage_url: str, email: str) -> dict[str, Any]:
        return self._post(
            "/internal/ingestion-requests",
            {
                "homepage_url": homepage_url,
                "email": email,
            },
        )

    def get_ingestion_request(
        self,
        *,
        request_id: int,
        request_token: str,
    ) -> dict[str, Any] | None:
        return self._get(
            f"/internal/ingestion-requests/{request_id}",
            {"request_token": request_token},
        )

    def list_priority_ingestion_requests(self) -> list[dict[str, Any]]:
        return self._get("/internal/ingestion-requests")

    def lookup_blog_candidates(self, *, url: str) -> dict[str, Any]:
        return self._get("/internal/blogs/lookup", {"url": url})

    def create_blog_dedup_scan_run(self, *, crawler_was_running: bool = False) -> dict[str, Any]:
        return self._post(
            f"/internal/blog-dedup-scans/runs?crawler_was_running={str(crawler_was_running).lower()}",
            {},
        )

    def create_url_refilter_run(self, *, crawler_was_running: bool = False) -> dict[str, Any]:
        return self._post(
            f"/internal/url-refilter-runs?crawler_was_running={str(crawler_was_running).lower()}",
            {},
        )

    def append_url_refilter_run_event(self, *, run_id: int, message: str) -> dict[str, Any]:
        return self._post(f"/internal/url-refilter-runs/{run_id}/events", {"message": message})

    def mark_url_refilter_run_failed(self, *, run_id: int, error_message: str) -> dict[str, Any]:
        return self._post(f"/internal/url-refilter-runs/{run_id}/failed", {"error_message": error_message})

    def execute_url_refilter_run(self, *, run_id: int) -> dict[str, Any]:
        return self._post(f"/internal/url-refilter-runs/{run_id}/execute", {})

    def latest_url_refilter_run(self) -> dict[str, Any]:
        return self._get("/internal/url-refilter-runs/latest")

    def list_url_refilter_run_events(self, run_id: int) -> list[dict[str, Any]]:
        return self._get(f"/internal/url-refilter-runs/{run_id}/events")

    def execute_blog_dedup_scan_run(self, *, run_id: int) -> dict[str, Any]:
        return self._post(f"/internal/blog-dedup-scans/{run_id}/execute", {})

    def finalize_blog_dedup_scan_run(
        self,
        *,
        run_id: int,
        crawler_restart_attempted: bool,
        crawler_restart_succeeded: bool,
        search_reindexed: bool,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        return self._post(
            f"/internal/blog-dedup-scans/{run_id}/finalize",
            {
                "crawler_restart_attempted": crawler_restart_attempted,
                "crawler_restart_succeeded": crawler_restart_succeeded,
                "search_reindexed": search_reindexed,
                "error_message": error_message,
            },
        )

    def latest_blog_dedup_scan_run(self) -> dict[str, Any]:
        return self._get("/internal/blog-dedup-scans/latest")

    def list_blog_dedup_scan_run_items(self, run_id: int) -> list[dict[str, Any]]:
        return self._get(f"/internal/blog-dedup-scans/{run_id}/items")

    def get_next_priority_blog(self) -> dict[str, Any] | None:
        return self._get("/internal/queue/priority-next")

    def get_next_waiting_blog(self, *, include_priority: bool = True) -> dict[str, Any] | None:
        return self._get("/internal/queue/next", {"include_priority": str(include_priority).lower()})

    def mark_ingestion_request_crawling(self, *, blog_id: int) -> None:
        self._post(f"/internal/ingestion-requests/by-blog/{blog_id}/crawling", {})

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

    def create_raw_discovered_url(
        self,
        *,
        source_blog_id: int,
        normalized_url: str,
        status: str,
    ) -> int:
        payload = self._post(
            "/internal/raw-discovered-urls",
            {
                "source_blog_id": source_blog_id,
                "normalized_url": normalized_url,
                "status": status,
            },
        )
        return int(payload["id"])

    def update_raw_discovered_url_status(self, *, record_id: int, status: str) -> None:
        self._put(f"/internal/raw-discovered-urls/{record_id}/status", {"status": status})

    def list_blogs_catalog(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        site: str | None = None,
        url: str | None = None,
        status: str | None = None,
        statuses: str | None = None,
        q: str | None = None,
        sort: str = "id_desc",
        has_title: bool | None = None,
        has_icon: bool | None = None,
        min_connections: int | None = None,
    ) -> dict[str, Any]:
        return self._get(
            "/internal/blogs/catalog",
            {
                "page": page,
                "page_size": page_size,
                "site": site,
                "url": url,
                "status": status,
                "statuses": statuses,
                "q": q,
                "sort": sort,
                "has_title": has_title,
                "has_icon": has_icon,
                "min_connections": min_connections,
            },
        )

    def list_blog_labeling_candidates(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        q: str | None = None,
        label: str | None = None,
        labeled: bool | None = None,
        sort: str = "id_desc",
    ) -> dict[str, Any]:
        return self._get(
            "/internal/blog-labeling/candidates",
            {
                "page": page,
                "page_size": page_size,
                "q": q,
                "label": label,
                "labeled": labeled,
                "sort": sort,
            },
        )

    def list_blog_label_tags(self) -> list[dict[str, Any]]:
        return self._get("/internal/blog-labeling/tags")

    def create_blog_label_tag(self, *, name: str) -> dict[str, Any]:
        return self._post("/internal/blog-labeling/tags", {"name": name})

    def replace_blog_link_labels(self, *, blog_id: int, tag_ids: list[int]) -> dict[str, Any]:
        return self._put(
            f"/internal/blog-labeling/labels/{blog_id}",
            {
                "tag_ids": tag_ids,
            },
        )

    def export_blog_label_training_csv(self) -> str:
        return self._get_text("/internal/blog-labeling/export")

    def get_blog_detail(self, blog_id: int) -> dict[str, Any]:
        return self._get(f"/internal/blogs/{blog_id}/detail")

    def stats(self) -> dict[str, Any]:
        return self._get("/internal/stats")

    def filter_stats(self) -> dict[str, Any]:
        return self._get("/internal/filter-stats")

    def get_filter_stats_by_chain_order(self) -> dict[str, Any]:
        return self.filter_stats()

    def graph_status(self) -> dict[str, Any]:
        return self._get("/internal/graph/status")

    def rebuild_graph_shadow(self) -> dict[str, Any]:
        return self._post("/internal/graph/shadow/rebuild", {})

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
