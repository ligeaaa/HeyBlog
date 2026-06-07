"""Public backend service that aggregates internal services."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import socket
from threading import Thread
from time import sleep
from typing import Any
from typing import Callable
from typing import NoReturn
from urllib.parse import urlsplit

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from crawler.crawling.metadata import extract_site_metadata
from shared.config import Settings
from shared.http_clients.crawler_http import CrawlerHttpClient
from shared.http_clients.persistence_http import PersistenceHttpClient
from shared.http_clients.search_http import SearchHttpClient
from shared.observability import RequestIdMiddleware
from shared.observability import configure_logging
from shared.observability import get_logger
from shared.observability import log_event


SERVICE_NAME = "backend"
LOGGER = get_logger(__name__)


@dataclass(slots=True)
class BackendState:
    """State container for the backend service."""

    persistence: Any
    crawler: Any
    search: Any
    maintenance_in_progress: bool = False
    admin_token: str | None = None
    admin_dev_bypass: bool = False


class RunBatchRequest(BaseModel):
    max_nodes: int


class CreateUserSeedRequest(BaseModel):
    homepage_url: str


class UserAuthRequest(BaseModel):
    email: str
    password: str


class ReplaceBlogLabelsRequest(BaseModel):
    tag_ids: list[int] | None = None
    label_id: dict[str, int] | None = None
    title: str | None = None


class IncrementBlogUserLabelRequest(BaseModel):
    label: str
    previous_label: str | None = None


class CreateRandomRecommendationBatchRequest(BaseModel):
    count: int = 9
    visitor_id: str
    session_id: str
    source: str | None = None
    page_url: str | None = None
    context: dict[str, Any] | None = None


class RecordRecommendationEventRequest(BaseModel):
    event_uuid: str
    event_type: str
    blog_id: int
    visitor_id: str
    session_id: str
    entrance_kind: str
    entrance_url: str
    request_uuid: str | None = None
    impression_id: int | None = None
    position: int | None = None
    interaction_order: int = 1
    client_event_at: str | None = None
    attributes: dict[str, Any] | None = None


class BlogLabelTitlePreviewRequest(BaseModel):
    url: str


class CreateBlogLabelTagRequest(BaseModel):
    name: str


ACTIVE_CRAWLER_RUNNER_STATUSES = frozenset({"starting", "running", "stopping"})
ICON_PROXY_MAX_BYTES = 1_000_000
ICON_PROXY_ALLOWED_SCHEMES = frozenset({"http", "https"})
ICON_PROXY_IMAGE_EXTENSIONS = (".ico", ".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif", ".avif")


def _is_private_icon_proxy_host(hostname: str) -> bool:
    """Return whether one hostname resolves to local or private network space.

    Args:
        hostname: Parsed URL hostname to validate before proxying.

    Returns:
        True when the hostname itself or any resolved address is unsafe for the
        public icon proxy.
    """
    try:
        ip_addresses = [ipaddress.ip_address(hostname)]
    except ValueError:
        try:
            resolved = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        except socket.gaierror:
            return True
        ip_addresses = []
        for item in resolved:
            address = item[4][0]
            try:
                ip_addresses.append(ipaddress.ip_address(address))
            except ValueError:
                return True

    return any(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        for address in ip_addresses
    )


def _validate_icon_proxy_url(url: str) -> str:
    """Normalize and validate a remote icon URL before proxying it.

    Args:
        url: User-supplied absolute URL.

    Returns:
        The trimmed URL when it is an allowed public HTTP(S) URL.

    Raises:
        HTTPException: If the URL is unsupported or points at unsafe address
            space.
    """
    clean_url = url.strip()
    parsed = urlsplit(clean_url)
    if parsed.scheme.lower() not in ICON_PROXY_ALLOWED_SCHEMES or not parsed.hostname:
        raise HTTPException(status_code=422, detail="unsupported_icon_url")
    if _is_private_icon_proxy_host(parsed.hostname):
        raise HTTPException(status_code=422, detail="unsafe_icon_url")
    return clean_url


def _is_image_like_icon_response(response: httpx.Response) -> bool:
    """Return whether one HTTP response looks like an icon image.

    Args:
        response: HTTP response from the remote icon URL.

    Returns:
        True when the content type is image-like, or a generic binary response
        has a known image file extension.
    """
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type.startswith("image/"):
        return True
    if content_type in {"application/octet-stream", "binary/octet-stream"}:
        return urlsplit(str(response.url)).path.lower().endswith(ICON_PROXY_IMAGE_EXTENSIONS)
    return False


def _fetch_icon_proxy_response(url: str) -> Response:
    """Fetch one remote icon and return it as a same-origin image response.

    Args:
        url: Validated public HTTP(S) icon URL.

    Returns:
        FastAPI response containing the icon bytes.

    Raises:
        HTTPException: If the remote URL cannot be fetched, is too large, or
            does not return an image-like response.
    """
    try:
        current_url = url
        for _ in range(4):
            with httpx.stream(
                "GET",
                current_url,
                follow_redirects=False,
                timeout=8.0,
                headers={"User-Agent": "HeyBlogBot/0.1 (+https://example.invalid/heyblog)"},
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308} and response.headers.get("location"):
                    current_url = _validate_icon_proxy_url(str(httpx.URL(str(response.url)).join(response.headers["location"])))
                    continue
                response.raise_for_status()
                if not _is_image_like_icon_response(response):
                    raise HTTPException(status_code=502, detail="icon_proxy_not_image")
                content_length = response.headers.get("content-length")
                if content_length is not None:
                    try:
                        if int(content_length) > ICON_PROXY_MAX_BYTES:
                            raise HTTPException(status_code=502, detail="icon_proxy_too_large")
                    except ValueError:
                        pass
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > ICON_PROXY_MAX_BYTES:
                        raise HTTPException(status_code=502, detail="icon_proxy_too_large")
                    chunks.append(chunk)
                content_type = response.headers.get("content-type", "image/x-icon")
                return Response(
                    content=b"".join(chunks),
                    media_type=content_type,
                    headers={"cache-control": "public, max-age=86400"},
                )
        raise HTTPException(status_code=502, detail="icon_proxy_too_many_redirects")
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="icon_proxy_timeout") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"icon_proxy_http_{exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="icon_proxy_fetch_failed") from exc


def _crawler_runtime_is_active(runtime: dict[str, Any]) -> bool:
    """Return whether one crawler runtime payload represents an active run."""
    return runtime.get("runner_status") in ACTIVE_CRAWLER_RUNNER_STATUSES


def _raise_for_maintenance(state: BackendState) -> None:
    if state.maintenance_in_progress:
        raise HTTPException(status_code=409, detail="maintenance_in_progress")


def _enter_maintenance(state: BackendState) -> bool:
    """Mark the backend as in maintenance mode and report whether crawler was active."""
    _raise_for_maintenance(state)
    runtime_before = state.crawler.runtime_status()
    crawler_was_running = _crawler_runtime_is_active(runtime_before)
    state.maintenance_in_progress = True
    return crawler_was_running


def _leave_maintenance(state: BackendState) -> None:
    """Clear backend maintenance mode."""
    state.maintenance_in_progress = False


def _stop_active_crawler(
    state: BackendState,
    *,
    crawler_was_running: bool,
    wait_for_idle: Callable[[], Any],
) -> None:
    """Stop the crawler and wait for idle only when it was active."""
    if not crawler_was_running:
        return
    state.crawler.stop()
    wait_for_idle()


def _upstream_error_detail(exc: httpx.HTTPStatusError, default: Any = "upstream_error") -> Any:
    """Extract a stable detail payload from an upstream HTTP failure."""
    try:
        return exc.response.json().get("detail", default)
    except Exception:  # noqa: BLE001
        return default


def _preview_label_title(url: str) -> dict[str, str | None]:
    """Fetch one candidate URL and extract a temporary display title.

    Args:
        url: Candidate URL whose HTML title should be fetched.

    Returns:
        Mapping containing the original URL and extracted title, if any.

    Raises:
        HTTPException: If the URL is invalid or cannot be fetched quickly.
    """

    clean_url = url.strip()
    if not clean_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="unsupported_url")
    try:
        response = httpx.get(
            clean_url,
            follow_redirects=True,
            timeout=5.0,
            headers={"User-Agent": "HeyBlogBot/0.1 (+https://example.invalid/heyblog)"},
        )
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="title_fetch_timeout") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="title_fetch_failed") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"title_fetch_http_{exc.response.status_code}") from exc
    metadata = extract_site_metadata(str(response.url), response.text)
    return {"url": clean_url, "title": metadata.title}


def _raise_upstream_http_error(
    exc: httpx.HTTPStatusError,
    *,
    default: Any = "upstream_error",
    detail_override: Any | None = None,
) -> None:
    """Re-raise an upstream HTTP failure with FastAPI-compatible semantics."""
    detail = detail_override if detail_override is not None else _upstream_error_detail(exc, default)
    raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc


def _call_upstream_with_http_error_translation(
    action: Callable[[], Any],
    *,
    default: Any = "upstream_error",
    detail_override: Any | None = None,
) -> Any:
    """Execute one upstream call and preserve the shared HTTP error mapping."""
    try:
        return action()
    except httpx.HTTPStatusError as exc:
        _raise_upstream_http_error(exc, default=default, detail_override=detail_override)


def _best_effort_search_reindex(search: Any) -> bool:
    """Try to rebuild search state and report whether it succeeded."""
    try:
        search.reindex()
        log_event(
            LOGGER,
            event="search.reindex.succeeded",
            message="search reindex succeeded",
            stage="search_reindex",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        log_event(
            LOGGER,
            event="search.reindex.failed",
            message="search reindex failed",
            level=30,
            stage="search_reindex",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        return False


def _run_crawler_action_and_refresh_search(
    search: Any,
    action: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Run one crawler action and best-effort refresh search before returning."""
    result = _call_upstream_with_http_error_translation(action)
    _best_effort_search_reindex(search)
    return result


def build_backend_state(settings: Settings | None = None) -> BackendState:
    """Build the backend service state."""
    resolved = settings or Settings.from_env()
    return BackendState(
        persistence=PersistenceHttpClient(
            resolved.persistence_base_url,
            timeout_seconds=resolved.request_timeout_seconds,
        ),
        crawler=CrawlerHttpClient(
            resolved.crawler_base_url,
            timeout_seconds=max(resolved.request_timeout_seconds, 60.0),
        ),
        search=SearchHttpClient(
            resolved.search_base_url,
            timeout_seconds=resolved.request_timeout_seconds,
        ),
        admin_token=resolved.admin_token,
        admin_dev_bypass=resolved.admin_dev_bypass,
    )


def create_app(state: BackendState | None = None) -> FastAPI:
    """Create the public backend app."""
    settings = Settings.from_env()
    configure_logging(
        service=SERVICE_NAME,
        log_dir=settings.log_dir,
        level=settings.log_level,
        file_enabled=settings.log_file_enabled,
        console_enabled=settings.log_console_enabled,
        log_format=settings.log_format,
        retention_days=settings.log_retention_days,
    )
    app = FastAPI(title="HeyBlog Backend Service", version="0.1.0")
    app.add_middleware(RequestIdMiddleware, service=SERVICE_NAME)
    app.state.backend_state = state or build_backend_state()

    def get_state() -> BackendState:
        return app.state.backend_state

    def require_admin_access(request: Request) -> None:
        state = get_state()
        if state.admin_dev_bypass:
            return
        if not state.admin_token:
            raise HTTPException(status_code=503, detail="admin_auth_not_configured")
        authorization = request.headers.get("authorization", "").strip()
        if not authorization:
            raise HTTPException(status_code=401, detail="admin_auth_required")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="admin_auth_required")
        if token != state.admin_token:
            raise HTTPException(status_code=403, detail="admin_auth_invalid")

    def optional_user(request: Request) -> dict[str, Any] | None:
        authorization = request.headers.get("authorization", "").strip()
        if not authorization:
            return None
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="auth_required")
        try:
            return get_state().persistence.get_user_by_session_token(token=token)
        except httpx.HTTPStatusError as exc:
            _raise_upstream_http_error(exc, default="auth_required", detail_override="auth_required")

    def require_user(request: Request) -> dict[str, Any]:
        user = optional_user(request)
        if user is None:
            raise HTTPException(status_code=401, detail="auth_required")
        return user

    def ensure_runtime_idle(*, retries: int = 120, delay_seconds: float = 0.5) -> dict[str, Any]:
        last_runtime = get_state().crawler.runtime_status()
        for _ in range(retries):
            if last_runtime.get("runner_status") == "idle":
                return last_runtime
            sleep(delay_seconds)
            last_runtime = get_state().crawler.runtime_status()
        raise HTTPException(status_code=409, detail="crawler_stop_timeout")

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "name": "HeyBlog Backend",
            "status": "/api/status",
            "panel": "served-by-frontend",
        }

    @app.get("/internal/health")
    def health() -> dict[str, str]:
        state = get_state()
        try:
            # Probe the three upstream services the backend must aggregate before
            # we report the backend as healthy to Compose or external checks.
            state.persistence.stats()
            state.crawler.runtime_status()
            state.search.search("")
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail="upstream_unavailable") from exc
        return {"status": "ok"}

    @app.get("/api/status")
    def get_status() -> dict[str, Any]:
        stats = get_state().persistence.stats()
        runtime = get_state().crawler.runtime_status()
        return {
            "is_running": _crawler_runtime_is_active(runtime),
            "pending_tasks": stats["pending_tasks"],
            "processing_tasks": stats["processing_tasks"],
            "finished_tasks": stats["finished_tasks"],
            "failed_tasks": stats["failed_tasks"],
            "total_blogs": stats["total_blogs"],
            "total_edges": stats["total_edges"],
        }

    @app.get("/api/blogs/catalog")
    def get_blogs_catalog(
        page: int = 1,
        page_size: int = 50,
        site: str | None = None,
        url: str | None = None,
        status: str | None = None,
        statuses: str | None = None,
        q: str | None = None,
        sort: str = "id_desc",
        has_title: str | None = None,
        has_icon: str | None = None,
        min_connections: str | None = None,
        acceptance_status: str | None = "ACCEPTED",
    ) -> dict[str, Any]:
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.list_blogs_catalog(
                page=page,
                page_size=page_size,
                site=site,
                url=url,
                status=status,
                statuses=statuses,
                q=q,
                sort=sort,
                has_title=has_title,
                has_icon=has_icon,
                min_connections=min_connections,
                acceptance_status=acceptance_status,
            )
        )

    @app.get("/api/blogs/lookup")
    def lookup_blog_candidates(url: str) -> dict[str, Any]:
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.lookup_blog_candidates(url=url)
        )

    @app.post("/api/recommendations/random-blog-batches")
    def post_random_recommendation_batch(
        payload: CreateRandomRecommendationBatchRequest,
        user: dict[str, Any] | None = Depends(optional_user),
    ) -> dict[str, Any]:
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.create_random_recommendation_batch(
                **payload.model_dump(),
                user_id=int(user["id"]) if user is not None else None,
            )
        )

    @app.post("/api/recommendation-events")
    def post_recommendation_event(
        payload: RecordRecommendationEventRequest,
        user: dict[str, Any] | None = Depends(optional_user),
    ) -> dict[str, Any]:
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.record_blog_interaction(
                **payload.model_dump(),
                user_id=int(user["id"]) if user is not None else None,
            )
        )

    @app.get("/api/blogs/{blog_id}/stats")
    def get_blog_recommendation_stats(blog_id: int) -> dict[str, Any]:
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.get_blog_recommendation_stats(blog_id)
        )

    @app.get("/api/admin/recommendation-stats")
    def get_admin_recommendation_stats(_: None = Depends(require_admin_access)) -> dict[str, Any]:
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.get_recommendation_strategy_stats()
        )

    @app.get("/api/icons/proxy")
    def proxy_icon(url: str) -> Response:
        """Return one remote icon through the backend origin for graph textures.

        Args:
            url: Absolute HTTP(S) icon URL to fetch.

        Returns:
            Image response with cache headers when the remote resource is valid.
        """
        return _fetch_icon_proxy_response(_validate_icon_proxy_url(url))

    @app.post("/api/auth/register")
    def register_user(payload: UserAuthRequest) -> dict[str, Any]:
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.register_user(email=payload.email, password=payload.password)
        )

    @app.post("/api/auth/login")
    def login_user(payload: UserAuthRequest) -> dict[str, Any]:
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.login_user(email=payload.email, password=payload.password)
        )

    @app.get("/api/auth/me")
    def get_current_user(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        return user

    @app.post("/api/auth/logout")
    def logout_user(request: Request, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        del user
        _, _, token = request.headers.get("authorization", "").strip().partition(" ")
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.revoke_user_session(token=token)
        )

    @app.get("/api/me/label-selections")
    def get_my_label_selections(
        limit: int = 50,
        user: dict[str, Any] = Depends(require_user),
    ) -> list[dict[str, Any]]:
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.list_user_label_selections(user_id=int(user["id"]), limit=limit)
        )

    @app.get("/api/me/label-stats")
    def get_my_label_stats(user: dict[str, Any] = Depends(require_user)) -> dict[str, int]:
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.get_user_label_stats(user_id=int(user["id"]))
        )

    @app.get("/api/admin/blog-labeling/candidates")
    def get_blog_labeling_candidates(
        page: int = 1,
        page_size: int = 50,
        q: str | None = None,
        label: str | None = None,
        labeled: str | None = None,
        sort: str = "id_desc",
        _: None = Depends(require_admin_access),
    ) -> dict[str, Any]:
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.list_blog_labeling_candidates(
                page=page,
                page_size=page_size,
                q=q,
                label=label,
                labeled=labeled,
                sort=sort,
            )
        )

    @app.get("/api/admin/blog-labeling/tags")
    def get_blog_label_tags(_: None = Depends(require_admin_access)) -> list[dict[str, Any]]:
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.list_blog_label_tags()
        )

    @app.post("/api/admin/blog-labeling/tags")
    def post_blog_label_tag(
        payload: CreateBlogLabelTagRequest,
        _: None = Depends(require_admin_access),
    ) -> dict[str, Any]:
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.create_blog_label_tag(name=payload.name)
        )

    @app.get("/api/admin/blog-labeling/counts")
    def get_blog_label_counts(_: None = Depends(require_admin_access)) -> dict[str, Any]:
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.get_blog_label_counts()
        )

    @app.post("/api/admin/blog-labeling/title-preview")
    def post_blog_label_title_preview(
        payload: BlogLabelTitlePreviewRequest,
        _: None = Depends(require_admin_access),
    ) -> dict[str, str | None]:
        return _preview_label_title(payload.url)

    @app.put("/api/admin/blog-labeling/labels/{blog_id}")
    def put_blog_labels(
        blog_id: int,
        payload: ReplaceBlogLabelsRequest,
        _: None = Depends(require_admin_access),
    ) -> dict[str, Any]:
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.replace_blog_link_labels(
                blog_id=blog_id,
                tag_ids=payload.tag_ids,
                label_id=payload.label_id,
                title=payload.title,
            )
        )

    @app.post("/api/blogs/{blog_id}/user-labels")
    def post_blog_user_label(
        blog_id: int,
        payload: IncrementBlogUserLabelRequest,
        user: dict[str, Any] | None = Depends(optional_user),
    ) -> dict[str, Any]:
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.increment_blog_user_label(
                blog_id=blog_id,
                label=payload.label,
                previous_label=payload.previous_label,
                user_id=int(user["id"]) if user is not None else None,
            )
        )

    @app.get("/api/admin/blog-labeling/parquet-status")
    def get_blog_label_training_parquet_status(_: None = Depends(require_admin_access)) -> dict[str, Any]:
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.get_blog_label_training_parquet_status()
        )

    @app.post("/api/admin/blog-labeling/parquet-sync")
    def sync_blog_label_training_parquet(_: None = Depends(require_admin_access)) -> dict[str, Any]:
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.sync_blog_label_training_parquet()
        )

    @app.post("/api/admin/blog-labeling/parquet-rebuild")
    def rebuild_blog_label_training_parquet(_: None = Depends(require_admin_access)) -> dict[str, Any]:
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.rebuild_blog_label_training_parquet()
        )

    @app.get("/api/admin/blog-labeling/parquet-export")
    def export_blog_label_training_parquet(_: None = Depends(require_admin_access)) -> Response:
        parquet_payload, headers = _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.export_blog_label_training_parquet()
        )
        return Response(
            content=parquet_payload,
            media_type="application/vnd.apache.parquet",
            headers={
                "content-disposition": headers.get(
                    "content-disposition",
                    'attachment; filename="blog-label-training.parquet"',
                ),
                "x-heyblog-label-saved-count": headers.get("x-heyblog-label-saved-count", "0"),
                "x-heyblog-label-total-count": headers.get("x-heyblog-label-total-count", "0"),
            },
        )

    @app.get("/api/blogs/{blog_id}")
    def get_blog(blog_id: int) -> dict[str, Any]:
        try:
            blog = get_state().persistence.get_blog_detail(blog_id)
        except httpx.HTTPStatusError as exc:
            detail_override = "Blog not found" if exc.response.status_code == 404 else None
            _raise_upstream_http_error(exc, detail_override=detail_override)
        if blog is None:
            raise HTTPException(status_code=404, detail="Blog not found")
        return blog

    @app.get("/api/graph/views/core")
    def get_graph_view(
        strategy: str = "degree",
        limit: int = 180,
        sample_mode: str = "off",
        sample_value: float | None = None,
        sample_seed: int = 7,
    ) -> dict[str, Any]:
        return get_state().persistence.graph_view(
            strategy=strategy,
            limit=limit,
            sample_mode=sample_mode,
            sample_value=sample_value,
            sample_seed=sample_seed,
        )

    @app.get("/api/graph/nodes/{blog_id}/neighbors")
    def get_graph_neighbors(blog_id: int, hops: int = 1, limit: int = 120) -> dict[str, Any]:
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.graph_neighbors(blog_id, hops=hops, limit=limit)
        )

    @app.get("/api/graph/snapshots/latest")
    def get_latest_graph_snapshot() -> dict[str, Any]:
        return get_state().persistence.latest_graph_snapshot()

    @app.get("/api/graph/snapshots/{version}")
    def get_graph_snapshot(version: str) -> dict[str, Any]:
        return get_state().persistence.graph_snapshot(version)

    @app.get("/api/stats")
    def get_stats() -> dict[str, Any]:
        return get_state().persistence.stats()

    @app.get("/api/filter-stats")
    def get_filter_stats() -> dict[str, Any]:
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.get_filter_stats_by_chain_order()
        )

    @app.post("/api/admin/crawl/bootstrap")
    def bootstrap(_: None = Depends(require_admin_access)) -> dict[str, Any]:
        return get_state().crawler.bootstrap()

    @app.post("/api/admin/crawl/run")
    def run_crawl(max_nodes: int | None = None, _: None = Depends(require_admin_access)) -> dict[str, Any]:
        state = get_state()
        return _run_crawler_action_and_refresh_search(
            state.search,
            lambda: state.crawler.run(max_nodes=max_nodes),
        )

    @app.post("/api/blogs/user-seeds")
    def create_user_seed(payload: CreateUserSeedRequest) -> dict[str, Any]:
        result = _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.create_user_seed(**payload.model_dump())
        )
        log_event(
            LOGGER,
            event="blog.user_seed.created",
            message="user seed created",
            stage="ingestion",
            run_id=result.get("blog_id"),
            url=payload.homepage_url,
        )
        return result

    @app.get("/api/admin/runtime/status")
    def runtime_status(_: None = Depends(require_admin_access)) -> dict[str, Any]:
        payload = get_state().crawler.runtime_status()
        payload["maintenance_in_progress"] = bool(get_state().maintenance_in_progress)
        return payload

    @app.get("/api/admin/runtime/current")
    def runtime_current(_: None = Depends(require_admin_access)) -> dict[str, Any]:
        return get_state().crawler.current()

    @app.post("/api/admin/runtime/start")
    def runtime_start(_: None = Depends(require_admin_access)) -> dict[str, Any]:
        _raise_for_maintenance(get_state())
        return get_state().crawler.start()

    @app.post("/api/admin/runtime/stop")
    def runtime_stop(_: None = Depends(require_admin_access)) -> dict[str, Any]:
        return get_state().crawler.stop()

    @app.post("/api/admin/runtime/run-batch")
    def runtime_run_batch(
        payload: RunBatchRequest,
        _: None = Depends(require_admin_access),
    ) -> dict[str, Any]:
        state = get_state()
        _raise_for_maintenance(state)
        return _run_crawler_action_and_refresh_search(
            state.search,
            lambda: state.crawler.run_batch(payload.max_nodes),
        )

    @app.post("/api/admin/blogs/requeue-failed")
    def requeue_failed_blogs(_: None = Depends(require_admin_access)) -> dict[str, Any]:
        runtime = get_state().crawler.runtime_status()
        if _crawler_runtime_is_active(runtime):
            raise HTTPException(status_code=409, detail="crawler_busy")
        return _call_upstream_with_http_error_translation(
            lambda: get_state().persistence.requeue_failed_blogs()
        )

    @app.post("/api/admin/database/reset")
    def reset_database(_: None = Depends(require_admin_access)) -> dict[str, Any]:
        runtime = get_state().crawler.runtime_status()
        if _crawler_runtime_is_active(runtime):
            raise HTTPException(status_code=409, detail="crawler_busy")

        result = get_state().persistence.reset()
        try:
            result["search"] = get_state().search.reindex()
            result["search_reindexed"] = True
        except Exception as exc:  # noqa: BLE001
            result["search"] = None
            result["search_reindexed"] = False
            result["search_error"] = str(exc)
        return result

    return app


app = create_app()
