"""HTTP client wrapper for the persistence service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from shared.http_clients.context import context_header_kwargs

URL_REFILTER_EXECUTE_TIMEOUT_SECONDS = 24 * 7 * 60 * 60


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

    def _bool_query_value(self, value: bool) -> str:
        """Encode a bool query parameter using the persistence API format.

        Args:
            value: Boolean value that should be sent over the HTTP query string.

        Returns:
            Lowercase string form expected by the persistence service.
        """

        return str(value).lower()

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        response = self.client.post(path, json=payload, **context_header_kwargs())
        response.raise_for_status()
        return response.json()

    def _post_with_timeout(self, path: str, payload: dict[str, Any], *, timeout_seconds: float) -> Any:
        """POST JSON with a per-request timeout override.

        Args:
            path: API path relative to the configured persistence base URL.
            payload: JSON payload to send.
            timeout_seconds: Timeout override in seconds for this request.

        Returns:
            Decoded JSON payload returned by the persistence service.
        """

        response = self.client.post(
            path,
            json=payload,
            timeout=timeout_seconds,
            **context_header_kwargs(),
        )
        response.raise_for_status()
        return response.json()

    def _put(self, path: str, payload: dict[str, Any]) -> Any:
        response = self.client.put(path, json=payload, **context_header_kwargs())
        response.raise_for_status()
        return response.json()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = self.client.get(path, params=params, **context_header_kwargs())
        response.raise_for_status()
        return response.json()

    def _create_maintenance_run(self, runs_path: str, *, crawler_was_running: bool) -> dict[str, Any]:
        """Create a maintenance run using the shared bool-query POST skeleton.

        Args:
            runs_path: Collection path for the maintenance run family.
            crawler_was_running: Whether crawler runtime was active before the run.

        Returns:
            Decoded maintenance run summary returned by persistence service.
        """

        return self._post(
            f"{runs_path}?crawler_was_running={self._bool_query_value(crawler_was_running)}",
            {},
        )

    def _post_maintenance_run_action(
        self,
        runs_path: str,
        *,
        run_id: int,
        action: str,
        payload: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Post to an action endpoint under a maintenance run family.

        Args:
            runs_path: Collection path for the maintenance run family.
            run_id: Maintenance run identifier.
            action: Child action name such as `execute` or `failed`.
            payload: Optional JSON body for the action request.
            timeout_seconds: Optional per-request timeout override.

        Returns:
            Decoded JSON payload returned by persistence service.
        """

        path = f"{runs_path}/{run_id}/{action}"
        if timeout_seconds is not None:
            return self._post_with_timeout(path, payload or {}, timeout_seconds=timeout_seconds)
        return self._post(path, payload or {})

    def _get_latest_maintenance_run(self, runs_path: str) -> dict[str, Any]:
        """Load the latest summary from a maintenance run family.

        Args:
            runs_path: Collection path for the maintenance run family.

        Returns:
            Decoded latest-run payload returned by persistence service.
        """

        return self._get(f"{runs_path}/latest")

    def _list_maintenance_run_children(
        self,
        runs_path: str,
        *,
        run_id: int,
        child_resource: str,
    ) -> list[dict[str, Any]]:
        """Load child resources attached to one maintenance run.

        Args:
            runs_path: Collection path for the maintenance run family.
            run_id: Maintenance run identifier.
            child_resource: Child collection name such as `events` or `items`.

        Returns:
            Ordered child payload list returned by persistence service.
        """

        return self._get(f"{runs_path}/{run_id}/{child_resource}")

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

    def register_user(self, *, email: str, password: str) -> dict[str, Any]:
        """Create a user account through persistence.

        Args:
            email: User email address.
            password: Plaintext password sent over the internal service link.

        Returns:
            Auth payload containing token, expiry, and user profile.
        """

        return self._post("/internal/users/register", {"email": email, "password": password})

    def login_user(self, *, email: str, password: str) -> dict[str, Any]:
        """Authenticate a user through persistence.

        Args:
            email: User email address.
            password: Plaintext password sent over the internal service link.

        Returns:
            Auth payload containing token, expiry, and user profile.
        """

        return self._post("/internal/users/login", {"email": email, "password": password})

    def get_user_by_session_token(self, *, token: str) -> dict[str, Any] | None:
        """Load the user profile for one raw session token."""

        return self._get("/internal/users/me", {"session_token": token})

    def revoke_user_session(self, *, token: str) -> dict[str, Any]:
        """Revoke one user session token."""

        return self._post(f"/internal/users/logout?session_token={token}", {})

    def list_user_label_selections(self, *, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
        """Fetch recent random-page selections for one user."""

        return self._get(f"/internal/users/{user_id}/label-selections", {"limit": limit})

    def get_user_label_stats(self, *, user_id: int) -> dict[str, int]:
        """Fetch the current label-selection count for one user."""

        return self._get(f"/internal/users/{user_id}/label-stats")

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
        return self._create_maintenance_run(
            "/internal/blog-dedup-scans/runs",
            crawler_was_running=crawler_was_running,
        )

    def create_url_refilter_run(self, *, crawler_was_running: bool = False) -> dict[str, Any]:
        return self._create_maintenance_run(
            "/internal/url-refilter-runs",
            crawler_was_running=crawler_was_running,
        )

    def append_url_refilter_run_event(self, *, run_id: int, message: str) -> dict[str, Any]:
        return self._post(f"/internal/url-refilter-runs/{run_id}/events", {"message": message})

    def mark_url_refilter_run_failed(self, *, run_id: int, error_message: str) -> dict[str, Any]:
        return self._post_maintenance_run_action(
            "/internal/url-refilter-runs",
            run_id=run_id,
            action="failed",
            payload={"error_message": error_message},
        )

    def execute_url_refilter_run(self, *, run_id: int) -> dict[str, Any]:
        return self._post_maintenance_run_action(
            "/internal/url-refilter-runs",
            run_id=run_id,
            action="execute",
            timeout_seconds=URL_REFILTER_EXECUTE_TIMEOUT_SECONDS,
        )

    def latest_url_refilter_run(self) -> dict[str, Any]:
        return self._get_latest_maintenance_run("/internal/url-refilter-runs")

    def list_url_refilter_run_events(self, run_id: int) -> list[dict[str, Any]]:
        return self._list_maintenance_run_children(
            "/internal/url-refilter-runs",
            run_id=run_id,
            child_resource="events",
        )

    def execute_blog_dedup_scan_run(self, *, run_id: int) -> dict[str, Any]:
        return self._post_maintenance_run_action(
            "/internal/blog-dedup-scans",
            run_id=run_id,
            action="execute",
        )

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
        return self._get_latest_maintenance_run("/internal/blog-dedup-scans")

    def list_blog_dedup_scan_run_items(self, run_id: int) -> list[dict[str, Any]]:
        return self._list_maintenance_run_children(
            "/internal/blog-dedup-scans",
            run_id=run_id,
            child_resource="items",
        )

    def get_next_priority_blog(self) -> dict[str, Any] | None:
        return self._get("/internal/queue/priority-next")

    def get_next_waiting_blog(self, *, include_priority: bool = True) -> dict[str, Any] | None:
        return self._get("/internal/queue/next", {"include_priority": self._bool_query_value(include_priority)})

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
        payload = self.create_raw_discovered_url_record(
            source_blog_id=source_blog_id,
            normalized_url=normalized_url,
            status=status,
        )
        return int(payload["id"])

    def create_raw_discovered_url_record(
        self,
        *,
        source_blog_id: int,
        normalized_url: str,
        status: str,
    ) -> dict[str, Any]:
        payload = self._post(
            "/internal/raw-discovered-urls",
            {
                "source_blog_id": source_blog_id,
                "normalized_url": normalized_url,
                "status": status,
            },
        )
        return {"id": int(payload["id"]), "status": str(payload["status"])}

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

    def get_blog_label_counts(self) -> dict[str, Any]:
        return self._get("/internal/blog-labeling/counts")

    def replace_blog_link_labels(
        self,
        *,
        blog_id: int,
        tag_ids: list[int] | None = None,
        label_id: dict[str, int] | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, object] = {}
        if tag_ids is not None:
            payload["tag_ids"] = tag_ids
        if label_id is not None:
            payload["label_id"] = label_id
        if title is not None:
            payload["title"] = title
        return self._put(
            f"/internal/blog-labeling/labels/{blog_id}",
            payload,
        )

    def increment_blog_user_label(
        self,
        *,
        blog_id: int,
        label: str,
        previous_label: str | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """Increment one public random-page label vote for a blog.

        Args:
            blog_id: Public/business blog ID.
            label: Label slug, name, or numeric ID to increment.
            previous_label: Optional page-local previous selection to
                decrement when the user switches labels.
            user_id: Optional registered user ID for persistent per-user
                selection tracking.

        Returns:
            Updated user-label state from persistence.
        """

        payload: dict[str, object] = {"label": label}
        if previous_label is not None:
            payload["previous_label"] = previous_label
        if user_id is not None:
            payload["user_id"] = user_id
        return self._post(f"/internal/blogs/{blog_id}/user-labels", payload)

    def get_blog_label_training_parquet_status(self) -> dict[str, Any]:
        """Fetch the current parquet export status for labeled training data.

        Returns:
            Status payload reported by the persistence service.
        """

        return self._get("/internal/blog-labeling/parquet-status")

    def sync_blog_label_training_parquet(self) -> dict[str, Any]:
        """Ask persistence to fill any missing labeled rows in the parquet export.

        Returns:
            Status payload after the sync check/save finishes.
        """

        return self._post("/internal/blog-labeling/parquet-sync", {})

    def rebuild_blog_label_training_parquet(self) -> dict[str, Any]:
        """Ask persistence to rebuild the parquet export from current labels.

        Returns:
            Status payload after the rebuild finishes.
        """

        return self._post("/internal/blog-labeling/parquet-rebuild", {})

    def export_blog_label_training_parquet(self) -> tuple[bytes, dict[str, str]]:
        """Download the current labeled training parquet payload.

        Returns:
            Tuple of response bytes and headers from persistence.
        """

        response = self.client.get("/internal/blog-labeling/parquet-export", **context_header_kwargs())
        response.raise_for_status()
        return response.content, dict(response.headers)

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
