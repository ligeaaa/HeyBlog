"""HTTP client wrapper for the persistence service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from shared.http_clients.context import context_header_kwargs


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
        feed_url: str | None = None,
        accepted_by: str | None = None,
        seed_source_path: str | None = None,
        seed_source_row: int | None = None,
    ) -> tuple[int, bool]:
        payload = self._post(
            "/internal/blogs/upsert",
            {
                "url": url,
                "normalized_url": normalized_url,
                "domain": domain,
                "email": email,
                "feed_url": feed_url,
                "accepted_by": accepted_by,
                "seed_source_path": seed_source_path,
                "seed_source_row": seed_source_row,
            },
        )
        return int(payload["id"]), bool(payload["inserted"])

    def list_seeds(self) -> list[dict[str, Any]]:
        """Fetch durable seed rows from persistence in replay order.

        Args:
            None.

        Returns:
            Seed payloads ordered by insertion ID.
        """

        return self._get("/internal/seeds")

    def create_random_recommendation_batch(
        self,
        *,
        count: int = 9,
        visitor_id: str,
        session_id: str,
        user_id: int | None = None,
        source: str | None = None,
        page_url: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create and persist one random-blog recommendation batch.

        Args:
            count: Number of random cards requested.
            visitor_id: Stable anonymous visitor identifier.
            session_id: Stable browser-session identifier.
            user_id: Optional authenticated user ID.
            source: Optional caller/source label.
            page_url: Optional frontend page URL.
            context: Optional JSON metadata.

        Returns:
            Recommendation batch payload returned by persistence.
        """

        return self._post(
            "/internal/recommendations/random-blog-batches",
            {
                "count": count,
                "visitor_id": visitor_id,
                "session_id": session_id,
                "user_id": user_id,
                "source": source,
                "page_url": page_url,
                "context": context,
            },
        )

    def record_blog_interaction(
        self,
        *,
        event_uuid: str,
        event_type: str,
        blog_id: int,
        visitor_id: str,
        session_id: str,
        entrance_kind: str,
        entrance_url: str,
        request_uuid: str | None = None,
        impression_id: int | None = None,
        position: int | None = None,
        interaction_order: int = 1,
        user_id: int | None = None,
        client_event_at: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist one random-blog recommendation interaction event.

        Args:
            event_uuid: Client idempotency key.
            event_type: Interaction type.
            blog_id: Public/business blog ID.
            visitor_id: Stable anonymous visitor identifier.
            session_id: Stable browser-session identifier.
            entrance_kind: Stable entrance category for the UI location.
            entrance_url: Raw URL for the entrance context.
            request_uuid: Optional recommendation request UUID.
            impression_id: Optional impression ID.
            position: Optional displayed card position.
            interaction_order: Client-side event order.
            user_id: Optional authenticated user ID.
            client_event_at: Optional client timestamp.
            attributes: Optional JSON metadata.

        Returns:
            Interaction payload returned by persistence.
        """

        return self._post(
            "/internal/recommendation-events",
            {
                "event_uuid": event_uuid,
                "event_type": event_type,
                "blog_id": blog_id,
                "visitor_id": visitor_id,
                "session_id": session_id,
                "entrance_kind": entrance_kind,
                "entrance_url": entrance_url,
                "request_uuid": request_uuid,
                "impression_id": impression_id,
                "position": position,
                "interaction_order": interaction_order,
                "user_id": user_id,
                "client_event_at": client_event_at,
                "attributes": attributes,
            },
        )

    def get_blog_recommendation_stats(self, blog_id: int) -> dict[str, Any]:
        """Load recommendation stats for one blog.

        Args:
            blog_id: Public/business blog ID.

        Returns:
            Stats payload returned by persistence.
        """

        return self._get(f"/internal/blogs/{blog_id}/recommendation-stats")

    def get_recommendation_strategy_stats(self) -> dict[str, Any]:
        """Load aggregate recommendation strategy stats.

        Args:
            None.

        Returns:
            Aggregate stats payload returned by persistence.
        """

        return self._get("/internal/recommendation-stats")

    def create_user_seed(self, *, homepage_url: str) -> dict[str, Any]:
        """Create or refresh a user-submitted crawler seed.

        Args:
            homepage_url: Complete user-submitted blog homepage URL.

        Returns:
            Accepted seed payload returned by persistence.
        """

        return self._post(
            "/internal/user-seeds",
            {
                "homepage_url": homepage_url,
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

    def lookup_blog_candidates(self, *, url: str) -> dict[str, Any]:
        return self._get("/internal/blogs/lookup", {"url": url})

    def find_blog_id_by_normalized_url(self, *, normalized_url: str) -> int | None:
        """Fetch the persisted blog id for one normalized URL."""

        payload = self._get("/internal/blogs/by-normalized-url", {"normalized_url": normalized_url})
        blog_id = payload.get("id")
        return int(blog_id) if blog_id is not None else None

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
        crawl_error_kind: str | None = None,
        crawl_error_message: str | None = None,
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
                "crawl_error_kind": crawl_error_kind,
                "crawl_error_message": crawl_error_message,
            },
        )

    def requeue_failed_blogs(self) -> dict[str, Any]:
        """Move all failed blogs back into the waiting crawler queue."""
        return self._post("/internal/blogs/requeue-failed", {})

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

    def update_raw_discovered_url_status(
        self,
        *,
        record_id: int,
        status: str,
        accepted_by: str | None = None,
    ) -> None:
        self._put(
            f"/internal/raw-discovered-urls/{record_id}/status",
            {"status": status, "accepted_by": accepted_by},
        )

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
        acceptance_status: str | None = "ACCEPTED",
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
                "acceptance_status": acceptance_status,
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
