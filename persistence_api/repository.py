"""SQLAlchemy-backed persistence repository."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from dataclasses import field
from datetime import UTC, datetime
from io import StringIO
import json
from math import ceil
from pathlib import Path
import sqlite3
from secrets import token_urlsafe
import re
from typing import Any
from typing import Protocol
from urllib.parse import urlparse

from sqlalchemy import and_
from sqlalchemy import case
from sqlalchemy import cast
from sqlalchemy import func
from sqlalchemy import inspect
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy import String
from sqlalchemy import text
from sqlalchemy.orm import Session

from persistence_api.db import create_persistence_engine
from persistence_api.db import create_session_factory
from persistence_api.db import session_scope
from persistence_api.models import Base
from persistence_api.models import BlogLabelAssignmentModel
from persistence_api.models import BlogLabelTagModel
from persistence_api.models import BlogModel
from persistence_api.models import BlogDedupScanRunItemModel
from persistence_api.models import BlogDedupScanRunModel
from persistence_api.models import EdgeModel
from persistence_api.models import IngestionRequestModel
from persistence_api.models import RawDiscoveredUrlModel
from persistence_api.models import UrlRefilterRunEventModel
from persistence_api.models import UrlRefilterRunModel
from persistence_api.recommendations import collect_friends_of_friends_candidates
from crawler.crawling.decisions.chain import build_url_decision_chain
from crawler.crawling.decisions.base import UrlCandidateContext
from crawler.crawling.normalization import IDENTITY_RULESET_VERSION
from crawler.crawling.normalization import BlogIdentityResolution
from crawler.crawling.normalization import normalize_url
from crawler.crawling.normalization import resolve_blog_identity
from shared.contracts.enums import CrawlStatus
from shared.config import Settings

BLOG_CATALOG_ALLOWED_STATUSES = frozenset({status.value for status in CrawlStatus})
BLOG_CATALOG_DEFAULT_PAGE_SIZE = 50
BLOG_CATALOG_MAX_PAGE_SIZE = 200
BLOG_CATALOG_DEFAULT_SORT = "id_desc"
BLOG_CATALOG_ALLOWED_SORTS = frozenset(
    {"id_asc", "id_desc", "recent_activity", "connections", "recently_discovered", "random"}
)
INGESTION_PRIORITY_LIST_LIMIT = 20
BLOG_LABELING_DEFAULT_PAGE_SIZE = 50
BLOG_LABELING_MAX_PAGE_SIZE = 200
BLOG_LABELING_DEFAULT_SORT = "id_desc"
BLOG_LABELING_ALLOWED_SORTS = frozenset({"id_desc", "recent_activity", "recently_labeled"})
INGESTION_REQUEST_STATUS_RECEIVED = "RECEIVED"
INGESTION_REQUEST_STATUS_DEDUPED_EXISTING = "DEDUPED_EXISTING"
INGESTION_REQUEST_STATUS_QUEUED = "QUEUED"
INGESTION_REQUEST_STATUS_CRAWLING_SEED = "CRAWLING_SEED"
INGESTION_REQUEST_STATUS_COMPLETED = "COMPLETED"
INGESTION_REQUEST_STATUS_FAILED = "FAILED"
INGESTION_REQUEST_STATUS_EXPIRED = "EXPIRED"
ACTIVE_INGESTION_REQUEST_STATUSES = frozenset(
    {
        INGESTION_REQUEST_STATUS_RECEIVED,
        INGESTION_REQUEST_STATUS_QUEUED,
        INGESTION_REQUEST_STATUS_CRAWLING_SEED,
    }
)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class BlogLabelingError(Exception):
    """Base error for blog labeling flows."""


class BlogLabelingNotFoundError(BlogLabelingError):
    """Raised when the target blog does not exist."""


class BlogLabelingConflictError(BlogLabelingError):
    """Raised when the target blog is not eligible for labeling."""


def slugify_blog_label(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not normalized:
        raise ValueError("Unsupported blog label name")
    return normalized


def now_utc() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(UTC)


def _sortable_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _business_blog_id(model: BlogModel | None) -> int | None:
    """Return the stable business blog identifier for one blog row."""
    if model is None:
        return None
    if model.blog_id is None:
        raise ValueError("blog_id_not_initialized")
    return int(model.blog_id)


def _dump_reason_codes(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=True)


def _load_reason_codes(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [str(item) for item in payload]


def normalize_ingestion_email(email: str) -> str:
    """Normalize and validate one user-supplied contact email."""
    normalized = email.strip().lower()
    if not normalized or not EMAIL_PATTERN.match(normalized):
        raise ValueError("Unsupported email address")
    return normalized


def _uses_tenant_root_canonicalization(reason_codes: list[str]) -> bool:
    return "tenant_subdomain_collapsed" in reason_codes


def _storage_url_and_domain(
    *,
    input_url: str,
    input_normalized_url: str,
    input_domain: str,
    identity: BlogIdentityResolution,
) -> tuple[str, str]:
    if _uses_tenant_root_canonicalization(identity.reason_codes):
        return identity.canonical_url, identity.canonical_host

    normalized = normalize_url(input_url or input_normalized_url)
    domain = normalized.domain or input_domain.strip().lower()
    return normalized.normalized_url, domain


def normalize_homepage_url(homepage_url: str) -> tuple[str, str, str, str, list[str], str]:
    """Normalize one homepage URL and reject obviously invalid inputs."""
    identity = resolve_blog_identity(homepage_url)
    normalized = normalize_url(homepage_url)
    use_tenant_root = _uses_tenant_root_canonicalization(identity.reason_codes)
    storage_url = identity.canonical_url if use_tenant_root else normalized.normalized_url
    storage_domain = identity.canonical_host if use_tenant_root else normalized.domain
    parsed = urlparse(storage_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Unsupported homepage URL")
    return (
        homepage_url.strip(),
        storage_url,
        storage_domain,
        identity.identity_key,
        identity.reason_codes,
        identity.ruleset_version,
    )


def _normalize_catalog_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_catalog_bool(value: bool | str | None) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ValueError(f"Unsupported boolean value: {value}")


def _normalize_catalog_int(value: int | str | None) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return max(value, 0)
    normalized = value.strip()
    if not normalized:
        return 0
    try:
        return max(int(normalized), 0)
    except ValueError as exc:
        raise ValueError(f"Unsupported integer value: {value}") from exc


def normalize_blog_catalog_query(
    *,
    page: int = 1,
    page_size: int = BLOG_CATALOG_DEFAULT_PAGE_SIZE,
    site: str | None = None,
    url: str | None = None,
    status: str | None = None,
    statuses: str | None = None,
    q: str | None = None,
    sort: str = BLOG_CATALOG_DEFAULT_SORT,
    has_title: bool | str | None = None,
    has_icon: bool | str | None = None,
    min_connections: int | str | None = None,
) -> dict[str, Any]:
    """Normalize catalog query params into one shared spec."""
    normalized_statuses: list[str] | None = None
    if statuses is not None:
        normalized_statuses = []
        for chunk in statuses.split(","):
            normalized_chunk = _normalize_catalog_text(chunk)
            if normalized_chunk is None:
                continue
            normalized_chunk = normalized_chunk.upper()
            if normalized_chunk not in BLOG_CATALOG_ALLOWED_STATUSES:
                raise ValueError(f"Unsupported crawl status: {normalized_chunk}")
            if normalized_chunk not in normalized_statuses:
                normalized_statuses.append(normalized_chunk)
        if not normalized_statuses:
            normalized_statuses = None

    normalized_status = _normalize_catalog_text(status)
    if normalized_status is not None and normalized_statuses is None:
        normalized_status = normalized_status.upper()
        if normalized_status not in BLOG_CATALOG_ALLOWED_STATUSES:
            raise ValueError(f"Unsupported crawl status: {normalized_status}")
    elif normalized_statuses is not None:
        normalized_status = None

    normalized_sort = _normalize_catalog_text(sort) or BLOG_CATALOG_DEFAULT_SORT
    if normalized_sort not in BLOG_CATALOG_ALLOWED_SORTS:
        raise ValueError(f"Unsupported blog catalog sort: {normalized_sort}")

    return {
        "page": max(page, 1),
        "page_size": max(1, min(page_size, BLOG_CATALOG_MAX_PAGE_SIZE)),
        "site": _normalize_catalog_text(site),
        "url": _normalize_catalog_text(url),
        "status": normalized_status,
        "statuses": normalized_statuses,
        "q": _normalize_catalog_text(q),
        "sort": normalized_sort,
        "has_title": _normalize_catalog_bool(has_title),
        "has_icon": _normalize_catalog_bool(has_icon),
        "min_connections": _normalize_catalog_int(min_connections),
    }


def normalize_blog_label(value: str | None) -> str | None:
    normalized = _normalize_catalog_text(value)
    if normalized is None:
        return None
    return slugify_blog_label(normalized)


def normalize_blog_labeling_query(
    *,
    page: int = 1,
    page_size: int = BLOG_LABELING_DEFAULT_PAGE_SIZE,
    q: str | None = None,
    label: str | None = None,
    labeled: bool | str | None = None,
    sort: str = BLOG_LABELING_DEFAULT_SORT,
) -> dict[str, Any]:
    normalized_sort = _normalize_catalog_text(sort) or BLOG_LABELING_DEFAULT_SORT
    if normalized_sort not in BLOG_LABELING_ALLOWED_SORTS:
        raise ValueError(f"Unsupported blog labeling sort: {normalized_sort}")

    return {
        "page": max(page, 1),
        "page_size": max(1, min(page_size, BLOG_LABELING_MAX_PAGE_SIZE)),
        "q": _normalize_catalog_text(q),
        "label": normalize_blog_label(label),
        "labeled": _normalize_catalog_bool(labeled),
        "sort": normalized_sort,
    }


def _catalog_response(
    *,
    items: list[dict[str, Any]],
    page: int,
    page_size: int,
    total_items: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    total_pages = ceil(total_items / page_size) if total_items else 0
    effective_page = 1 if total_pages == 0 else min(page, total_pages)
    return {
        "items": items,
        "page": effective_page,
        "page_size": page_size,
        "total_items": total_items,
        "total_pages": total_pages,
        "has_next": total_pages > 0 and effective_page < total_pages,
        "has_prev": total_pages > 0 and effective_page > 1,
        "filters": filters,
        "sort": filters["sort"],
    }


def ensure_legacy_compat_schema(engine: Any) -> None:
    """Apply additive compatibility fixes needed by existing persistence databases."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    if "blogs" not in existing_tables or "ingestion_requests" not in existing_tables:
        return
    blog_columns = {column["name"] for column in inspector.get_columns("blogs")}
    ingestion_columns = {column["name"] for column in inspector.get_columns("ingestion_requests")}
    with engine.begin() as connection:
        if "email" not in blog_columns:
            connection.execute(text("ALTER TABLE blogs ADD COLUMN email TEXT"))
        if "identity_key" not in blog_columns:
            connection.execute(text("ALTER TABLE blogs ADD COLUMN identity_key TEXT"))
        if "identity_reason_codes" not in blog_columns:
            connection.execute(
                text("ALTER TABLE blogs ADD COLUMN identity_reason_codes TEXT DEFAULT '[]' NOT NULL")
            )
        if "identity_ruleset_version" not in blog_columns:
            connection.execute(
                text("ALTER TABLE blogs ADD COLUMN identity_ruleset_version TEXT DEFAULT '' NOT NULL")
            )
        if "identity_key" not in ingestion_columns:
            connection.execute(text("ALTER TABLE ingestion_requests ADD COLUMN identity_key TEXT"))
        if "identity_reason_codes" not in ingestion_columns:
            connection.execute(
                text(
                    "ALTER TABLE ingestion_requests ADD COLUMN identity_reason_codes TEXT DEFAULT '[]' NOT NULL"
                )
            )
        if "identity_ruleset_version" not in ingestion_columns:
            connection.execute(
                text(
                    "ALTER TABLE ingestion_requests ADD COLUMN identity_ruleset_version TEXT DEFAULT '' NOT NULL"
                )
            )
        if "blog_dedup_scan_runs" in existing_tables:
            run_columns = {column["name"] for column in inspector.get_columns("blog_dedup_scan_runs")}
            if "total_count" not in run_columns:
                connection.execute(
                    text("ALTER TABLE blog_dedup_scan_runs ADD COLUMN total_count INTEGER DEFAULT 0 NOT NULL")
                )
        if "ix_blogs_identity_key" not in {index["name"] for index in inspector.get_indexes("blogs")}:
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_blogs_identity_key ON blogs (identity_key)"))
        if "ix_ingestion_requests_identity_key" not in {
            index["name"] for index in inspector.get_indexes("ingestion_requests")
        }:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_ingestion_requests_identity_key "
                    "ON ingestion_requests (identity_key)"
                )
            )
        if (
            "blog_link_labels" in existing_tables
            and "blog_label_tags" in existing_tables
            and "blog_label_assignments" in existing_tables
        ):
            old_columns = {column["name"] for column in inspector.get_columns("blog_link_labels")}
            if {"blog_id", "label"}.issubset(old_columns):
                legacy_rows = connection.execute(
                    text("SELECT blog_id, label, labeled_at, created_at, updated_at FROM blog_link_labels")
                ).mappings().all()
                for row in legacy_rows:
                    slug = slugify_blog_label(str(row["label"]))
                    existing_tag = connection.execute(
                        text("SELECT id FROM blog_label_tags WHERE slug = :slug"),
                        {"slug": slug},
                    ).scalar()
                    if existing_tag is None:
                        connection.execute(
                            text(
                                "INSERT INTO blog_label_tags (name, slug, created_at, updated_at) "
                                "VALUES (:name, :slug, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                            ),
                            {"name": str(row["label"]), "slug": slug},
                        )
                        existing_tag = connection.execute(
                            text("SELECT id FROM blog_label_tags WHERE slug = :slug"),
                            {"slug": slug},
                        ).scalar()
                    existing_assignment = connection.execute(
                        text(
                            "SELECT id FROM blog_label_assignments "
                            "WHERE blog_id = :blog_id AND tag_id = :tag_id"
                        ),
                        {"blog_id": row["blog_id"], "tag_id": existing_tag},
                    ).scalar()
                    if existing_assignment is None:
                        connection.execute(
                            text(
                                "INSERT INTO blog_label_assignments "
                                "(blog_id, tag_id, labeled_at, created_at, updated_at) "
                                "VALUES (:blog_id, :tag_id, :labeled_at, :created_at, :updated_at)"
                            ),
                            {
                                "blog_id": row["blog_id"],
                                "tag_id": existing_tag,
                                "labeled_at": row["labeled_at"] or now_utc(),
                                "created_at": row["created_at"] or now_utc(),
                                "updated_at": row["updated_at"] or now_utc(),
                            },
                        )
        blog_rows = connection.execute(
            text(
                "SELECT id, blog_id, url, normalized_url, domain, identity_key, identity_ruleset_version "
                "FROM blogs"
            )
        ).mappings().all()
        for row in blog_rows:
            needs_refresh = (
                not row["identity_key"]
                or str(row["identity_ruleset_version"] or "") != IDENTITY_RULESET_VERSION
            )
            if not needs_refresh:
                continue
            identity = resolve_blog_identity(str(row["url"]) or str(row["normalized_url"]))
            connection.execute(
                text(
                    "UPDATE blogs SET identity_key = :identity_key, identity_reason_codes = :reason_codes, "
                    "identity_ruleset_version = :ruleset_version, domain = :domain "
                    "WHERE id = :blog_id"
                ),
                {
                    "blog_id": row["id"],
                    "identity_key": identity.identity_key,
                    "reason_codes": _dump_reason_codes(identity.reason_codes),
                    "ruleset_version": identity.ruleset_version,
                    "domain": str(row["domain"] or identity.domain),
                },
            )
        ingestion_rows = connection.execute(
            text(
                "SELECT id, requested_url, normalized_url, identity_key, identity_ruleset_version "
                "FROM ingestion_requests"
            )
        ).mappings().all()
        for row in ingestion_rows:
            needs_refresh = (
                not row["identity_key"]
                or str(row["identity_ruleset_version"] or "") != IDENTITY_RULESET_VERSION
            )
            if not needs_refresh:
                continue
            identity = resolve_blog_identity(str(row["requested_url"]) or str(row["normalized_url"]))
            storage_url = (
                identity.canonical_url
                if _uses_tenant_root_canonicalization(identity.reason_codes)
                else normalize_url(str(row["requested_url"]) or str(row["normalized_url"])).normalized_url
            )
            connection.execute(
                text(
                    "UPDATE ingestion_requests SET identity_key = :identity_key, "
                    "identity_reason_codes = :reason_codes, identity_ruleset_version = :ruleset_version, "
                    "normalized_url = :normalized_url "
                    "WHERE id = :request_id"
                ),
                {
                    "request_id": row["id"],
                    "identity_key": identity.identity_key,
                    "reason_codes": _dump_reason_codes(identity.reason_codes),
                    "ruleset_version": identity.ruleset_version,
                    "normalized_url": storage_url,
                },
            )


def _blog_payload(
    model: BlogModel,
    *,
    incoming_count: int = 0,
    outgoing_count: int = 0,
    activity_at: datetime | None = None,
    identity_complete: bool | None = None,
) -> dict[str, Any]:
    resolved_incoming_count = int(incoming_count)
    resolved_outgoing_count = int(outgoing_count)
    resolved_title = _resolved_blog_title(model)
    resolved_icon_url = _resolved_blog_icon_url(model)
    resolved_blog_id = _business_blog_id(model)
    return {
        "id": int(resolved_blog_id),
        "blog_id": int(resolved_blog_id),
        "url": model.url,
        "normalized_url": model.normalized_url,
        "identity_key": model.identity_key,
        "identity_reason_codes": _load_reason_codes(model.identity_reason_codes),
        "identity_ruleset_version": model.identity_ruleset_version,
        "domain": model.domain,
        "email": model.email,
        "title": resolved_title,
        "icon_url": resolved_icon_url,
        "status_code": model.status_code,
        "crawl_status": model.crawl_status.value,
        "friend_links_count": int(model.friend_links_count),
        "last_crawled_at": _iso(model.last_crawled_at),
        "created_at": _iso(model.created_at),
        "updated_at": _iso(model.updated_at),
        "incoming_count": resolved_incoming_count,
        "outgoing_count": resolved_outgoing_count,
        "connection_count": resolved_incoming_count + resolved_outgoing_count,
        "activity_at": _iso(activity_at or model.last_crawled_at or model.updated_at),
        "identity_complete": bool(
            identity_complete
            if identity_complete is not None
            else (bool(resolved_title) and bool(resolved_icon_url))
        ),
    }


def _resolved_blog_title(model: BlogModel) -> str:
    title = (model.title or "").strip()
    if title:
        return title
    return model.domain


def _resolved_blog_icon_url(model: BlogModel) -> str | None:
    icon_url = (model.icon_url or "").strip()
    if icon_url:
        return icon_url

    parsed = urlparse(model.url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}/favicon.ico"


def _edge_payload(model: EdgeModel) -> dict[str, Any]:
    return {
        "id": int(model.id),
        "from_blog_id": int(model.from_blog_id),
        "to_blog_id": int(model.to_blog_id),
        "link_url_raw": model.link_url_raw,
        "link_text": model.link_text,
        "discovered_at": _iso(model.discovered_at),
    }


def _neighbor_payload(model: BlogModel | None) -> dict[str, Any] | None:
    if model is None:
        return None
    return {
        "id": int(_business_blog_id(model)),
        "blog_id": int(_business_blog_id(model)),
        "domain": model.domain,
        "title": _resolved_blog_title(model),
        "icon_url": _resolved_blog_icon_url(model),
    }


def _public_blog_summary_payload(model: BlogModel | None) -> dict[str, Any] | None:
    if model is None:
        return None
    return {
        "id": int(_business_blog_id(model)),
        "blog_id": int(_business_blog_id(model)),
        "url": model.url,
        "normalized_url": model.normalized_url,
        "domain": model.domain,
        "title": _resolved_blog_title(model),
        "icon_url": _resolved_blog_icon_url(model),
        "crawl_status": model.crawl_status.value,
    }


def _ingestion_request_payload(
    model: IngestionRequestModel,
    *,
    seed_blog: BlogModel | None = None,
    matched_blog: BlogModel | None = None,
) -> dict[str, Any]:
    resolved_blog = matched_blog or seed_blog
    resolved_blog_id = None
    if matched_blog is not None:
        resolved_blog_id = _business_blog_id(matched_blog)
    elif seed_blog is not None:
        resolved_blog_id = _business_blog_id(seed_blog)
    return {
        "id": int(model.id),
        "request_id": int(model.id),
        "requested_url": model.requested_url,
        "normalized_url": model.normalized_url,
        "identity_key": model.identity_key,
        "identity_reason_codes": _load_reason_codes(model.identity_reason_codes),
        "identity_ruleset_version": model.identity_ruleset_version,
        "email": model.requester_email,
        "status": model.status,
        "priority": int(model.priority),
        "seed_blog_id": int(model.seed_blog_id) if model.seed_blog_id is not None else None,
        "matched_blog_id": int(model.matched_blog_id) if model.matched_blog_id is not None else None,
        "blog_id": resolved_blog_id,
        "request_token": model.request_token,
        "expires_at": _iso(model.expires_at),
        "error_message": model.error_message,
        "created_at": _iso(model.created_at),
        "updated_at": _iso(model.updated_at),
        "seed_blog": _blog_payload(seed_blog) if seed_blog is not None else None,
        "matched_blog": _blog_payload(matched_blog) if matched_blog is not None else None,
        "blog": _blog_payload(resolved_blog) if resolved_blog is not None else None,
    }


def _priority_ingestion_request_payload(
    model: IngestionRequestModel,
    *,
    seed_blog: BlogModel | None = None,
    matched_blog: BlogModel | None = None,
) -> dict[str, Any]:
    resolved_blog = matched_blog or seed_blog
    payload = _ingestion_request_payload(model, seed_blog=seed_blog, matched_blog=matched_blog)
    for key in (
        "id",
        "email",
        "identity_key",
        "identity_reason_codes",
        "identity_ruleset_version",
        "priority",
        "request_token",
        "expires_at",
        "seed_blog",
        "matched_blog",
    ):
        payload.pop(key, None)
    payload["blog"] = _public_blog_summary_payload(resolved_blog)
    return payload


def _blog_lookup_payload(
    *,
    query_url: str,
    normalized_query_url: str,
    items: list[dict[str, Any]],
    match_reason: str | None,
) -> dict[str, Any]:
    return {
        "query_url": query_url,
        "normalized_query_url": normalized_query_url,
        "items": items,
        "total_matches": len(items),
        "match_reason": match_reason,
    }


def _blog_label_tag_payload(model: BlogLabelTagModel) -> dict[str, Any]:
    return {
        "id": int(model.id),
        "name": model.name,
        "slug": model.slug,
        "created_at": _iso(model.created_at),
        "updated_at": _iso(model.updated_at),
    }


def _blog_dedup_scan_run_payload(model: BlogDedupScanRunModel) -> dict[str, Any]:
    return {
        "id": int(model.id),
        "status": model.status,
        "ruleset_version": model.ruleset_version,
        "started_at": _iso(model.started_at),
        "completed_at": _iso(model.completed_at),
        "duration_ms": int(model.duration_ms),
        "total_count": int(model.total_count),
        "scanned_count": int(model.scanned_count),
        "removed_count": int(model.removed_count),
        "kept_count": int(model.kept_count),
        "crawler_was_running": bool(model.crawler_was_running),
        "crawler_restart_attempted": bool(model.crawler_restart_attempted),
        "crawler_restart_succeeded": bool(model.crawler_restart_succeeded),
        "search_reindexed": bool(model.search_reindexed),
        "error_message": model.error_message,
        "created_at": _iso(model.created_at),
        "updated_at": _iso(model.updated_at),
    }


def _blog_dedup_scan_run_item_payload(model: BlogDedupScanRunItemModel) -> dict[str, Any]:
    return {
        "id": int(model.id),
        "run_id": int(model.run_id),
        "survivor_blog_id": int(model.survivor_blog_id) if model.survivor_blog_id is not None else None,
        "removed_blog_id": int(model.removed_blog_id) if model.removed_blog_id is not None else None,
        "survivor_identity_key": model.survivor_identity_key,
        "removed_url": model.removed_url,
        "removed_normalized_url": model.removed_normalized_url,
        "removed_domain": model.removed_domain,
        "reason_code": model.reason_code,
        "reason_codes": _load_reason_codes(model.reason_codes),
        "survivor_selection_basis": model.survivor_selection_basis,
        "created_at": _iso(model.created_at),
    }


def _url_refilter_run_payload(model: UrlRefilterRunModel) -> dict[str, Any]:
    return {
        "id": int(model.id),
        "status": model.status,
        "filter_chain_version": model.filter_chain_version,
        "crawler_was_running": bool(model.crawler_was_running),
        "backup_path": model.backup_path,
        "total_count": int(model.total_count),
        "scanned_count": int(model.scanned_count),
        "unchanged_count": int(model.unchanged_count),
        "activated_count": int(model.activated_count),
        "deactivated_count": int(model.deactivated_count),
        "retagged_count": int(model.retagged_count),
        "last_raw_url_id": int(model.last_raw_url_id) if model.last_raw_url_id is not None else None,
        "started_at": _iso(model.started_at),
        "completed_at": _iso(model.completed_at),
        "error_message": model.error_message,
        "created_at": _iso(model.created_at),
        "updated_at": _iso(model.updated_at),
    }


def _url_refilter_run_event_payload(model: UrlRefilterRunEventModel) -> dict[str, Any]:
    return {
        "id": int(model.id),
        "run_id": int(model.run_id),
        "message": model.message,
        "created_at": _iso(model.created_at),
    }


def _decision_scan_ruleset_version(settings: Settings) -> str:
    """Describe the current URL decision-chain configuration in one string.

    Args:
        settings: Runtime settings that determine which decision steps are
            active for crawler URL filtering.

    Returns:
        A compact version string suitable for storing in scan summaries.
    """
    if settings.decision_model_consensus_enabled:
        return "url_decision_chain:rule_based+model_consensus"
    return "url_decision_chain:rule_based"


def _filter_chain_version(settings: Settings) -> str:
    """Return one stable string describing the configured URL filter chain."""
    return "|".join(build_url_decision_chain(settings).ordered_statuses())


def _blog_labeling_payload(
    row: Any,
    *,
    labels: list[dict[str, Any]],
    last_labeled_at: datetime | None,
) -> dict[str, Any]:
    blog = row[0]
    return {
        **_blog_payload(
            blog,
            incoming_count=int(row.incoming_count or 0),
            outgoing_count=int(row.outgoing_count or 0),
            activity_at=row.activity_at,
            identity_complete=bool(row.identity_complete),
        ),
        "labels": labels,
        "label_slugs": [label["slug"] for label in labels],
        "last_labeled_at": _iso(last_labeled_at),
        "is_labeled": len(labels) > 0,
    }


def _recommended_blog_payload(
    *,
    blog: BlogModel,
    via_blogs: list[BlogModel],
    incoming_count: int = 0,
    outgoing_count: int = 0,
    activity_at: datetime | None = None,
    identity_complete: bool | None = None,
) -> dict[str, Any]:
    return {
        "blog": _blog_payload(
            blog,
            incoming_count=incoming_count,
            outgoing_count=outgoing_count,
            activity_at=activity_at,
            identity_complete=identity_complete,
        ),
        "reason": "mutual_connection",
        "mutual_connection_count": len(via_blogs),
        "via_blogs": [_neighbor_payload(via_blog) for via_blog in via_blogs if via_blog is not None],
    }


class RepositoryProtocol(Protocol):
    """Protocol shared by in-process and HTTP-backed repositories."""

    def add_log(
        self, stage: str, result: str, message: str, blog_id: int | None = None
    ) -> None: ...

    def upsert_blog(
        self,
        *,
        url: str,
        normalized_url: str,
        domain: str,
        email: str | None = None,
    ) -> tuple[int, bool]: ...

    def get_next_waiting_blog(self, *, include_priority: bool = True) -> dict[str, Any] | None: ...

    def get_next_priority_blog(self) -> dict[str, Any] | None: ...

    def create_ingestion_request(self, *, homepage_url: str, email: str) -> dict[str, Any]: ...

    def get_ingestion_request(
        self,
        *,
        request_id: int,
        request_token: str,
    ) -> dict[str, Any] | None: ...

    def list_priority_ingestion_requests(self, *, limit: int = INGESTION_PRIORITY_LIST_LIMIT) -> list[dict[str, Any]]: ...

    def lookup_blog_candidates(self, *, url: str) -> dict[str, Any]: ...

    def mark_ingestion_request_crawling(self, *, blog_id: int) -> None: ...

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
    ) -> None: ...

    def add_edge(
        self,
        *,
        from_blog_id: int,
        to_blog_id: int,
        link_url_raw: str,
        link_text: str | None,
    ) -> None: ...

    def create_raw_discovered_url(
        self,
        *,
        source_blog_id: int,
        normalized_url: str,
        status: str,
    ) -> int: ...

    def update_raw_discovered_url_status(self, *, record_id: int, status: str) -> None: ...

    def list_blogs(self) -> list[dict[str, Any]]: ...

    def list_blogs_catalog(
        self,
        *,
        page: int = 1,
        page_size: int = BLOG_CATALOG_DEFAULT_PAGE_SIZE,
        site: str | None = None,
        url: str | None = None,
        status: str | None = None,
        statuses: str | None = None,
        q: str | None = None,
        sort: str = BLOG_CATALOG_DEFAULT_SORT,
        has_title: bool | str | None = None,
        has_icon: bool | str | None = None,
        min_connections: int | None = None,
    ) -> dict[str, Any]: ...

    def list_blog_labeling_candidates(
        self,
        *,
        page: int = 1,
        page_size: int = BLOG_LABELING_DEFAULT_PAGE_SIZE,
        q: str | None = None,
        label: str | None = None,
        labeled: bool | str | None = None,
        sort: str = BLOG_LABELING_DEFAULT_SORT,
    ) -> dict[str, Any]: ...

    def list_blog_label_tags(self) -> list[dict[str, Any]]: ...

    def create_blog_label_tag(self, *, name: str) -> dict[str, Any]: ...

    def replace_blog_link_labels(self, *, blog_id: int, tag_ids: list[int]) -> dict[str, Any]: ...

    def export_blog_label_training_csv(self) -> str: ...

    def get_blog(self, blog_id: int) -> dict[str, Any] | None: ...

    def get_blog_detail(self, blog_id: int) -> dict[str, Any] | None: ...

    def list_edges(self) -> list[dict[str, Any]]: ...

    def list_logs(self, limit: int = 100) -> list[dict[str, Any]]: ...

    def stats(self) -> dict[str, Any]: ...

    def get_filter_stats_by_chain_order(self) -> dict[str, Any]: ...

    def create_url_refilter_run(self, *, crawler_was_running: bool = False) -> dict[str, Any]: ...

    def append_url_refilter_run_event(self, *, run_id: int, message: str) -> dict[str, Any]: ...

    def mark_url_refilter_run_failed(self, *, run_id: int, error_message: str) -> dict[str, Any]: ...

    def execute_url_refilter_run(self, *, run_id: int) -> dict[str, Any]: ...

    def get_latest_url_refilter_run(self) -> dict[str, Any] | None: ...

    def list_url_refilter_run_events(self, run_id: int) -> list[dict[str, Any]]: ...

    def create_blog_dedup_scan_run(self, *, crawler_was_running: bool = False) -> dict[str, Any]: ...

    def execute_blog_dedup_scan_run(self, *, run_id: int) -> dict[str, Any]: ...

    def finalize_blog_dedup_scan_run(
        self,
        *,
        run_id: int,
        crawler_restart_attempted: bool,
        crawler_restart_succeeded: bool,
        search_reindexed: bool,
        error_message: str | None = None,
    ) -> dict[str, Any]: ...

    def get_latest_blog_dedup_scan_run(self) -> dict[str, Any] | None: ...

    def list_blog_dedup_scan_run_items(self, run_id: int) -> list[dict[str, Any]]: ...

    def reset(self) -> dict[str, Any]: ...


@dataclass(slots=True)
class SQLAlchemyRepository:
    """Repository implemented with one SQLAlchemy engine."""

    database_url: str
    decision_settings: Settings | None = None
    startup_schema_sync: bool = True
    engine: Any = field(init=False, repr=False)
    session_factory: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.engine = create_persistence_engine(self.database_url)
        self.session_factory = create_session_factory(self.engine)
        if self.startup_schema_sync:
            Base.metadata.create_all(self.engine)
            ensure_legacy_compat_schema(self.engine)
        with session_scope(self.session_factory) as session:
            self._fail_orphaned_url_refilter_runs(session)
            self._fail_orphaned_dedup_scan_runs(session)
            self._requeue_processing(session)

    @property
    def dialect_name(self) -> str:
        return str(self.engine.dialect.name)

    def _requeue_processing(self, session: Session) -> None:
        session.query(BlogModel).filter(BlogModel.crawl_status == CrawlStatus.PROCESSING).update(
            {
                BlogModel.crawl_status: CrawlStatus.WAITING,
                BlogModel.updated_at: now_utc(),
            }
        )
        session.query(IngestionRequestModel).filter(
            IngestionRequestModel.status == INGESTION_REQUEST_STATUS_CRAWLING_SEED
        ).update(
            {
                IngestionRequestModel.status: INGESTION_REQUEST_STATUS_QUEUED,
                IngestionRequestModel.updated_at: now_utc(),
            }
        )

    def _fail_orphaned_dedup_scan_runs(self, session: Session) -> None:
        orphaned_runs = session.scalars(
            select(BlogDedupScanRunModel).where(BlogDedupScanRunModel.status == "RUNNING")
        ).all()
        if not orphaned_runs:
            return
        failed_at = now_utc()
        for run in orphaned_runs:
            started_at = _sortable_datetime(run.started_at)
            run.status = "FAILED"
            run.completed_at = failed_at
            run.duration_ms = max(int((failed_at - started_at).total_seconds() * 1000), 0)
            run.error_message = "orphaned_dedup_scan_run_cleaned_on_startup"
            run.updated_at = failed_at

    def _fail_orphaned_url_refilter_runs(self, session: Session) -> None:
        orphaned_runs = session.scalars(
            select(UrlRefilterRunModel).where(UrlRefilterRunModel.status == "RUNNING")
        ).all()
        if not orphaned_runs:
            return
        failed_at = now_utc()
        for run in orphaned_runs:
            run.status = "FAILED"
            run.completed_at = failed_at
            run.error_message = "orphaned_url_refilter_run_cleaned_on_startup"
            run.updated_at = failed_at
            self._append_url_refilter_run_event_in_session(
                session,
                run_id=int(run.id),
                message="重新过滤任务在服务重启后被标记为失败",
            )

    def _get_blog_by_business_id(self, session: Session, blog_id: int) -> BlogModel | None:
        """Return one blog row by business ``blog_id``."""
        return session.scalar(select(BlogModel).where(BlogModel.blog_id == blog_id))

    def _ensure_schema(self) -> None:
        ensure_legacy_compat_schema(self.engine)

    def _blog_labeling_select(self) -> tuple[Any, dict[str, Any]]:
        statement, metrics = self._blog_select()
        latest_labeled_at = (
            select(
                BlogLabelAssignmentModel.blog_id.label("blog_id"),
                func.max(BlogLabelAssignmentModel.labeled_at).label("last_labeled_at"),
            )
            .group_by(BlogLabelAssignmentModel.blog_id)
            .subquery()
        )
        statement = statement.outerjoin(
            latest_labeled_at,
            latest_labeled_at.c.blog_id == BlogModel.blog_id,
        ).add_columns(latest_labeled_at.c.last_labeled_at.label("last_labeled_at"))
        metrics["latest_labeled_at"] = latest_labeled_at.c.last_labeled_at
        return statement, metrics

    def _blog_metrics_expressions(self) -> dict[str, Any]:
        incoming_counts = (
            select(
                EdgeModel.to_blog_id.label("blog_id"),
                func.count(EdgeModel.id).label("incoming_count"),
            )
            .group_by(EdgeModel.to_blog_id)
            .subquery()
        )
        outgoing_counts = (
            select(
                EdgeModel.from_blog_id.label("blog_id"),
                func.count(EdgeModel.id).label("outgoing_count"),
            )
            .group_by(EdgeModel.from_blog_id)
            .subquery()
        )
        incoming_count = func.coalesce(incoming_counts.c.incoming_count, 0)
        outgoing_count = func.coalesce(outgoing_counts.c.outgoing_count, 0)
        connection_count = incoming_count + outgoing_count
        activity_at = func.coalesce(BlogModel.last_crawled_at, BlogModel.updated_at)
        identity_complete = case(
            (
                and_(
                    BlogModel.title.is_not(None),
                    BlogModel.title != "",
                    BlogModel.icon_url.is_not(None),
                    BlogModel.icon_url != "",
                ),
                True,
            ),
            else_=False,
        )
        return {
            "incoming_counts": incoming_counts,
            "outgoing_counts": outgoing_counts,
            "incoming_count": incoming_count,
            "outgoing_count": outgoing_count,
            "connection_count": connection_count,
            "activity_at": activity_at,
            "identity_complete": identity_complete,
        }

    def _blog_select(self) -> tuple[Any, dict[str, Any]]:
        metrics = self._blog_metrics_expressions()
        statement = (
            select(
                BlogModel,
                metrics["incoming_count"].label("incoming_count"),
                metrics["outgoing_count"].label("outgoing_count"),
                metrics["connection_count"].label("connection_count"),
                metrics["activity_at"].label("activity_at"),
                metrics["identity_complete"].label("identity_complete"),
            )
            .outerjoin(metrics["incoming_counts"], metrics["incoming_counts"].c.blog_id == BlogModel.blog_id)
            .outerjoin(metrics["outgoing_counts"], metrics["outgoing_counts"].c.blog_id == BlogModel.blog_id)
        )
        return statement, metrics

    def _row_blog_payload(self, row: Any) -> dict[str, Any]:
        return _blog_payload(
            row[0],
            incoming_count=int(row.incoming_count or 0),
            outgoing_count=int(row.outgoing_count or 0),
            activity_at=row.activity_at,
            identity_complete=bool(row.identity_complete),
        )

    def _ingestion_request_row_payload(
        self,
        session: Session,
        request: IngestionRequestModel,
    ) -> dict[str, Any]:
        seed_blog = (
            self._get_blog_by_business_id(session, request.seed_blog_id)
            if request.seed_blog_id is not None
            else None
        )
        matched_blog = (
            self._get_blog_by_business_id(session, request.matched_blog_id)
            if request.matched_blog_id is not None
            else None
        )
        return _ingestion_request_payload(request, seed_blog=seed_blog, matched_blog=matched_blog)

    def _resolve_identity_from_blog_fields(
        self,
        *,
        url: str,
        normalized_url: str,
    ) -> BlogIdentityResolution:
        return resolve_blog_identity(url or normalized_url)

    def _select_survivor(self, blogs: list[BlogModel]) -> tuple[BlogModel, str]:
        ranked = sorted(
            blogs,
            key=lambda blog: (
                len((blog.normalized_url or "").strip()),
                _sortable_datetime(blog.created_at),
                int(blog.id),
            ),
        )
        survivor = ranked[0]
        basis_parts = [f"normalized_url_length={len((survivor.normalized_url or '').strip())}"]
        basis_parts.append(f"normalized_url={survivor.normalized_url}")
        basis_parts.append(f"created_at={_iso(survivor.created_at)}")
        basis_parts.append(f"id={int(survivor.id)}")
        return survivor, ", ".join(basis_parts)

    def _decision_scan_settings(self) -> Settings:
        """Return the settings object used for administrative URL rescans.

        Returns:
            The injected persistence-service settings when available, or a
            minimal local fallback that keeps model consensus disabled for
            direct repository tests.
        """
        if self.decision_settings is not None:
            return self.decision_settings
        return Settings(
            db_path=Path("data/heyblog.sqlite"),
            seed_path=Path("seed.csv"),
            export_dir=Path("data/exports"),
            decision_model_consensus_enabled=False,
        )

    def _append_url_refilter_run_event_in_session(
        self,
        session: Session,
        *,
        run_id: int,
        message: str,
    ) -> UrlRefilterRunEventModel:
        event = UrlRefilterRunEventModel(
            run_id=run_id,
            message=message,
            created_at=now_utc(),
        )
        session.add(event)
        session.flush()
        return event

    def _backup_sqlite_database(self) -> str:
        """Create one timestamped SQLite backup and return the written path."""
        database_path = Path(str(self.engine.url.database)).resolve()
        backup_dir = self._decision_scan_settings().export_dir / "db-backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"heyblog-refilter-backup-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.sqlite"
        self.engine.dispose()
        source = sqlite3.connect(str(database_path))
        target = sqlite3.connect(str(backup_path))
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        return str(backup_path)

    def _upsert_blog_in_session(
        self,
        session: Session,
        *,
        url: str,
        normalized_url: str,
        domain: str,
        email: str | None = None,
    ) -> BlogModel:
        identity = self._resolve_identity_from_blog_fields(url=url, normalized_url=normalized_url)
        stored_url, stored_domain = _storage_url_and_domain(
            input_url=url,
            input_normalized_url=normalized_url,
            input_domain=domain,
            identity=identity,
        )
        existing = session.scalar(
            select(BlogModel).where(
                or_(
                    BlogModel.normalized_url == stored_url,
                    BlogModel.identity_key == identity.identity_key,
                )
            )
        )
        if existing is not None:
            if _uses_tenant_root_canonicalization(identity.reason_codes):
                existing.url = stored_url
                existing.normalized_url = stored_url
                existing.domain = stored_domain
            if email is not None and not (existing.email or "").strip():
                existing.email = email
            existing.identity_key = identity.identity_key
            existing.identity_reason_codes = _dump_reason_codes(identity.reason_codes)
            existing.identity_ruleset_version = identity.ruleset_version
            existing.updated_at = now_utc()
            return existing

        blog = BlogModel(
            blog_id=None,
            url=stored_url,
            normalized_url=stored_url,
            identity_key=identity.identity_key,
            identity_reason_codes=_dump_reason_codes(identity.reason_codes),
            identity_ruleset_version=identity.ruleset_version,
            domain=stored_domain,
            email=email,
            crawl_status=CrawlStatus.WAITING,
            friend_links_count=0,
            created_at=now_utc(),
            updated_at=now_utc(),
        )
        session.add(blog)
        session.flush()
        blog.blog_id = int(blog.id)
        session.flush()
        return blog

    def _ensure_edge_in_session(
        self,
        session: Session,
        *,
        from_blog_id: int,
        to_blog_id: int,
        link_url_raw: str,
        link_text: str | None,
    ) -> None:
        existing = session.scalar(
            select(EdgeModel).where(
                EdgeModel.from_blog_id == from_blog_id,
                EdgeModel.to_blog_id == to_blog_id,
            )
        )
        if existing is not None:
            return
        session.add(
            EdgeModel(
                from_blog_id=from_blog_id,
                to_blog_id=to_blog_id,
                link_url_raw=link_url_raw,
                link_text=link_text,
                discovered_at=now_utc(),
            )
        )

    def _handle_refilter_activated_success(
        self,
        session: Session,
        *,
        raw: RawDiscoveredUrlModel,
    ) -> None:
        normalized = normalize_url(raw.normalized_url)
        target_blog = self._upsert_blog_in_session(
            session,
            url=raw.normalized_url,
            normalized_url=normalized.normalized_url,
            domain=normalized.domain,
        )
        self._ensure_edge_in_session(
            session,
            from_blog_id=int(raw.source_blog_id),
            to_blog_id=int(_business_blog_id(target_blog)),
            link_url_raw=raw.normalized_url,
            link_text=None,
        )

    def _handle_refilter_deactivated_success(
        self,
        session: Session,
        *,
        raw: RawDiscoveredUrlModel,
    ) -> None:
        session.flush()
        identity = self._resolve_identity_from_blog_fields(url=raw.normalized_url, normalized_url=raw.normalized_url)
        normalized = normalize_url(raw.normalized_url)
        stored_url, _ = _storage_url_and_domain(
            input_url=raw.normalized_url,
            input_normalized_url=normalized.normalized_url,
            input_domain=normalized.domain,
            identity=identity,
        )
        target_blog = session.scalar(
            select(BlogModel).where(
                or_(
                    BlogModel.normalized_url == stored_url,
                    BlogModel.identity_key == identity.identity_key,
                )
            )
        )
        if target_blog is None:
            return
        session.query(EdgeModel).filter(
            EdgeModel.from_blog_id == int(raw.source_blog_id),
            EdgeModel.to_blog_id == int(_business_blog_id(target_blog)),
        ).delete(synchronize_session=False)
        remaining_success = int(
            session.scalar(
                select(func.count())
                .select_from(RawDiscoveredUrlModel)
                .where(
                    RawDiscoveredUrlModel.normalized_url == raw.normalized_url,
                    RawDiscoveredUrlModel.status == "success",
                )
            )
            or 0
        )
        if remaining_success == 0:
            self._delete_blog_graph(session, blog_id=int(_business_blog_id(target_blog)))
            session.flush()

    def _delete_blog_graph(self, session: Session, *, blog_id: int) -> None:
        """Delete one blog and its direct graph attachments safely.

        Args:
            session: Active database session used for the deletion.
            blog_id: Blog identifier that should be removed from persistence.

        Returns:
            ``None``. The blog, its edges, label assignments, and dangling
            ingestion references are removed or cleared in place.
        """
        session.query(EdgeModel).filter(
            or_(
                EdgeModel.from_blog_id == blog_id,
                EdgeModel.to_blog_id == blog_id,
            )
        ).delete(synchronize_session=False)
        session.query(BlogLabelAssignmentModel).filter(
            BlogLabelAssignmentModel.blog_id == blog_id
        ).delete(synchronize_session=False)
        session.query(IngestionRequestModel).filter(
            IngestionRequestModel.seed_blog_id == blog_id
        ).update({IngestionRequestModel.seed_blog_id: None})
        session.query(IngestionRequestModel).filter(
            IngestionRequestModel.matched_blog_id == blog_id
        ).update({IngestionRequestModel.matched_blog_id: None})
        blog = self._get_blog_by_business_id(session, blog_id)
        if blog is not None:
            session.delete(blog)

    def add_log(
        self, stage: str, result: str, message: str, blog_id: int | None = None
    ) -> None:
        """Crawler logs are no longer stored in the database."""
        return None

    def upsert_blog(
        self,
        *,
        url: str,
        normalized_url: str,
        domain: str,
        email: str | None = None,
    ) -> tuple[int, bool]:
        identity = self._resolve_identity_from_blog_fields(
            url=url,
            normalized_url=normalized_url,
        )
        stored_url, stored_domain = _storage_url_and_domain(
            input_url=url,
            input_normalized_url=normalized_url,
            input_domain=domain,
            identity=identity,
        )
        identity_key = identity.identity_key
        reason_codes = identity.reason_codes
        ruleset_version = identity.ruleset_version
        with session_scope(self.session_factory) as session:
            existing = session.scalar(
                select(BlogModel).where(
                    or_(
                        BlogModel.normalized_url == stored_url,
                        BlogModel.identity_key == identity_key,
                    )
                )
            )
            if existing is not None:
                if _uses_tenant_root_canonicalization(reason_codes):
                    existing.url = stored_url
                    existing.normalized_url = stored_url
                    existing.domain = stored_domain
                if email is not None and not (existing.email or "").strip():
                    existing.email = email
                existing.identity_key = identity_key
                existing.identity_reason_codes = _dump_reason_codes(reason_codes)
                existing.identity_ruleset_version = ruleset_version
                existing.updated_at = now_utc()
                return int(_business_blog_id(existing)), False

            blog = BlogModel(
                blog_id=None,
                url=stored_url,
                normalized_url=stored_url,
                identity_key=identity_key,
                identity_reason_codes=_dump_reason_codes(reason_codes),
                identity_ruleset_version=ruleset_version,
                domain=stored_domain,
                email=email,
                crawl_status=CrawlStatus.WAITING,
                friend_links_count=0,
                created_at=now_utc(),
                updated_at=now_utc(),
            )
            session.add(blog)
            session.flush()
            blog.blog_id = int(blog.id)
            session.flush()
            return int(_business_blog_id(blog)), True

    def create_ingestion_request(self, *, homepage_url: str, email: str) -> dict[str, Any]:
        requested_url, normalized_url, domain, identity_key, reason_codes, ruleset_version = normalize_homepage_url(
            homepage_url
        )
        normalized_email = normalize_ingestion_email(email)
        with session_scope(self.session_factory) as session:
            existing_blog = session.scalar(
                select(BlogModel).where(BlogModel.identity_key == identity_key)
            )
            if existing_blog is not None and not (existing_blog.email or "").strip():
                existing_blog.email = normalized_email
            if existing_blog is not None:
                if _uses_tenant_root_canonicalization(reason_codes):
                    existing_blog.url = normalized_url
                    existing_blog.normalized_url = normalized_url
                    existing_blog.domain = domain
                existing_blog.identity_key = identity_key
                existing_blog.identity_reason_codes = _dump_reason_codes(reason_codes)
                existing_blog.identity_ruleset_version = ruleset_version
                existing_blog.updated_at = now_utc()

            if existing_blog is not None and existing_blog.crawl_status == CrawlStatus.FINISHED:
                return {
                    "status": INGESTION_REQUEST_STATUS_DEDUPED_EXISTING,
                    "blog_id": int(_business_blog_id(existing_blog)),
                    "matched_blog_id": int(_business_blog_id(existing_blog)),
                    "request_id": None,
                    "request_token": None,
                    "blog": _blog_payload(existing_blog),
                }

            existing_request = session.scalar(
                select(IngestionRequestModel)
                .where(
                    IngestionRequestModel.identity_key == identity_key,
                    IngestionRequestModel.status.in_(tuple(ACTIVE_INGESTION_REQUEST_STATUSES)),
                )
                .order_by(IngestionRequestModel.created_at.asc(), IngestionRequestModel.id.asc())
            )
            if existing_request is not None:
                if not (existing_request.requester_email or "").strip():
                    existing_request.requester_email = normalized_email
                if _uses_tenant_root_canonicalization(reason_codes):
                    existing_request.normalized_url = normalized_url
                existing_request.identity_key = identity_key
                existing_request.identity_reason_codes = _dump_reason_codes(reason_codes)
                existing_request.identity_ruleset_version = ruleset_version
                existing_request.updated_at = now_utc()
                return self._ingestion_request_row_payload(session, existing_request)

            if existing_blog is None:
                existing_blog = BlogModel(
                    blog_id=None,
                    url=normalized_url,
                    normalized_url=normalized_url,
                    identity_key=identity_key,
                    identity_reason_codes=_dump_reason_codes(reason_codes),
                    identity_ruleset_version=ruleset_version,
                    domain=domain,
                    email=normalized_email,
                    crawl_status=CrawlStatus.WAITING,
                    friend_links_count=0,
                    created_at=now_utc(),
                    updated_at=now_utc(),
                )
                session.add(existing_blog)
                session.flush()
                existing_blog.blog_id = int(existing_blog.id)
                session.flush()
            elif existing_blog.crawl_status == CrawlStatus.FAILED:
                existing_blog.crawl_status = CrawlStatus.WAITING
                existing_blog.updated_at = now_utc()

            request_status = (
                INGESTION_REQUEST_STATUS_CRAWLING_SEED
                if existing_blog.crawl_status == CrawlStatus.PROCESSING
                else INGESTION_REQUEST_STATUS_QUEUED
            )
            request = IngestionRequestModel(
                requested_url=requested_url,
                normalized_url=normalized_url,
                identity_key=identity_key,
                identity_reason_codes=_dump_reason_codes(reason_codes),
                identity_ruleset_version=ruleset_version,
                requester_email=normalized_email,
                status=request_status,
                priority=100,
                seed_blog_id=int(_business_blog_id(existing_blog)),
                matched_blog_id=None,
                request_token=token_urlsafe(18),
                expires_at=None,
                error_message=None,
                created_at=now_utc(),
                updated_at=now_utc(),
            )
            session.add(request)
            session.flush()
            return self._ingestion_request_row_payload(session, request)

    def get_ingestion_request(
        self,
        *,
        request_id: int,
        request_token: str,
    ) -> dict[str, Any] | None:
        with session_scope(self.session_factory) as session:
            request = session.scalar(
                select(IngestionRequestModel).where(IngestionRequestModel.id == request_id)
            )
            if request is None or request.request_token != request_token:
                return None
            return self._ingestion_request_row_payload(session, request)

    def list_priority_ingestion_requests(self, *, limit: int = INGESTION_PRIORITY_LIST_LIMIT) -> list[dict[str, Any]]:
        resolved_limit = max(1, min(int(limit), INGESTION_PRIORITY_LIST_LIMIT))
        active_sort = case(
            (IngestionRequestModel.status.in_(tuple(ACTIVE_INGESTION_REQUEST_STATUSES)), 0),
            else_=1,
        )
        with session_scope(self.session_factory) as session:
            requests = session.scalars(
                select(IngestionRequestModel)
                .where(IngestionRequestModel.priority >= 100)
                .order_by(active_sort.asc(), IngestionRequestModel.created_at.desc(), IngestionRequestModel.id.desc())
                .limit(resolved_limit)
            ).all()
            payload: list[dict[str, Any]] = []
            for request in requests:
                seed_blog = (
                    self._get_blog_by_business_id(session, request.seed_blog_id)
                    if request.seed_blog_id is not None
                    else None
                )
                matched_blog = (
                    self._get_blog_by_business_id(session, request.matched_blog_id)
                    if request.matched_blog_id is not None
                    else None
                )
                payload.append(
                    _priority_ingestion_request_payload(
                        request,
                        seed_blog=seed_blog,
                        matched_blog=matched_blog,
                    )
                )
            return payload

    def lookup_blog_candidates(self, *, url: str) -> dict[str, Any]:
        normalized = normalize_url(url)
        identity = resolve_blog_identity(url)
        parsed = urlparse(identity.canonical_url if identity.is_homepage else normalized.normalized_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Unsupported homepage URL")
        query_url = url.strip()
        normalized_query_url = identity.canonical_url if identity.is_homepage else normalized.normalized_url
        identity_key = identity.identity_key
        with session_scope(self.session_factory) as session:
            identity_matches = session.scalars(
                select(BlogModel)
                .where(BlogModel.identity_key == identity_key)
                .order_by(BlogModel.blog_id.asc(), BlogModel.id.asc())
            ).all()
            if identity_matches:
                return _blog_lookup_payload(
                    query_url=query_url,
                    normalized_query_url=normalized_query_url,
                    items=[_blog_payload(item) for item in identity_matches],
                    match_reason="identity_key",
                )

            normalized_matches = session.scalars(
                select(BlogModel)
                .where(BlogModel.normalized_url == normalized_query_url)
                .order_by(BlogModel.blog_id.asc(), BlogModel.id.asc())
            ).all()
            if normalized_matches:
                return _blog_lookup_payload(
                    query_url=query_url,
                    normalized_query_url=normalized_query_url,
                    items=[_blog_payload(item) for item in normalized_matches],
                    match_reason="normalized_url",
                )

            return _blog_lookup_payload(
                query_url=query_url,
                normalized_query_url=normalized_query_url,
                items=[],
                match_reason=None,
            )

    def mark_ingestion_request_crawling(self, *, blog_id: int) -> None:
        with session_scope(self.session_factory) as session:
            request = session.scalar(
                select(IngestionRequestModel)
                .where(
                    IngestionRequestModel.seed_blog_id == blog_id,
                    IngestionRequestModel.status == INGESTION_REQUEST_STATUS_QUEUED,
                )
                .order_by(IngestionRequestModel.created_at.asc(), IngestionRequestModel.id.asc())
            )
            if request is None:
                return
            request.status = INGESTION_REQUEST_STATUS_CRAWLING_SEED
            request.updated_at = now_utc()

    def _claim_blog_for_statement(self, session: Session, statement: Any) -> dict[str, Any] | None:
        blog = session.scalar(statement)
        if blog is None:
            return None
        blog.crawl_status = CrawlStatus.PROCESSING
        blog.updated_at = now_utc()
        session.flush()
        return _blog_payload(blog)

    def get_next_priority_blog(self) -> dict[str, Any] | None:
        with session_scope(self.session_factory) as session:
            statement = (
                select(BlogModel)
                .join(
                    IngestionRequestModel,
                    IngestionRequestModel.seed_blog_id == BlogModel.blog_id,
                )
                .where(
                    BlogModel.crawl_status == CrawlStatus.WAITING,
                    IngestionRequestModel.status == INGESTION_REQUEST_STATUS_QUEUED,
                )
                .order_by(
                    IngestionRequestModel.priority.desc(),
                    IngestionRequestModel.created_at.asc(),
                    BlogModel.blog_id.asc(),
                    BlogModel.id.asc(),
                )
                .limit(1)
            )
            if self.dialect_name == "postgresql":
                statement = statement.with_for_update(skip_locked=True)
            return self._claim_blog_for_statement(session, statement)

    def get_next_waiting_blog(self, *, include_priority: bool = True) -> dict[str, Any] | None:
        with session_scope(self.session_factory) as session:
            statement = select(BlogModel).where(BlogModel.crawl_status == CrawlStatus.WAITING)
            if not include_priority:
                priority_seed_ids = (
                    select(IngestionRequestModel.seed_blog_id)
                    .where(
                        IngestionRequestModel.seed_blog_id.is_not(None),
                        IngestionRequestModel.status.in_(tuple(ACTIVE_INGESTION_REQUEST_STATUSES)),
                    )
                    .subquery()
                )
                statement = statement.where(BlogModel.blog_id.not_in(select(priority_seed_ids.c.seed_blog_id)))
            statement = statement.order_by(BlogModel.blog_id.asc(), BlogModel.id.asc()).limit(1)
            if self.dialect_name == "postgresql":
                statement = statement.with_for_update(skip_locked=True)
            return self._claim_blog_for_statement(session, statement)

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
        with session_scope(self.session_factory) as session:
            blog = self._get_blog_by_business_id(session, blog_id)
            if blog is None:
                return
            blog.crawl_status = CrawlStatus(crawl_status)
            blog.status_code = status_code
            blog.friend_links_count = friend_links_count
            blog.last_crawled_at = now_utc()
            blog.updated_at = now_utc()
            if metadata_captured:
                blog.title = title
                blog.icon_url = icon_url
            request = session.scalar(
                select(IngestionRequestModel)
                .where(
                    IngestionRequestModel.seed_blog_id == blog_id,
                    IngestionRequestModel.status.in_(tuple(ACTIVE_INGESTION_REQUEST_STATUSES)),
                )
                .order_by(IngestionRequestModel.created_at.asc(), IngestionRequestModel.id.asc())
            )
            if request is not None:
                if blog.crawl_status == CrawlStatus.FINISHED:
                    request.status = INGESTION_REQUEST_STATUS_COMPLETED
                    request.matched_blog_id = int(_business_blog_id(blog))
                    request.error_message = None
                elif blog.crawl_status == CrawlStatus.FAILED:
                    request.status = INGESTION_REQUEST_STATUS_FAILED
                    request.error_message = "seed crawl failed"
                request.updated_at = now_utc()

    def add_edge(
        self,
        *,
        from_blog_id: int,
        to_blog_id: int,
        link_url_raw: str,
        link_text: str | None,
    ) -> None:
        with session_scope(self.session_factory) as session:
            existing = session.scalar(
                select(EdgeModel).where(
                    EdgeModel.from_blog_id == from_blog_id,
                    EdgeModel.to_blog_id == to_blog_id,
                )
            )
            if existing is not None:
                return
            edge = EdgeModel(
                from_blog_id=from_blog_id,
                to_blog_id=to_blog_id,
                link_url_raw=link_url_raw,
                link_text=link_text,
                discovered_at=now_utc(),
            )
            session.add(edge)

    def create_raw_discovered_url(
        self,
        *,
        source_blog_id: int,
        normalized_url: str,
        status: str,
    ) -> int:
        with session_scope(self.session_factory) as session:
            record = RawDiscoveredUrlModel(
                source_blog_id=source_blog_id,
                normalized_url=normalized_url,
                status=status,
                discovered_at=now_utc(),
                updated_at=now_utc(),
            )
            session.add(record)
            session.flush()
            return int(record.id)

    def update_raw_discovered_url_status(self, *, record_id: int, status: str) -> None:
        with session_scope(self.session_factory) as session:
            record = session.get(RawDiscoveredUrlModel, record_id)
            if record is None:
                raise ValueError("raw_discovered_url_not_found")
            record.status = status
            record.updated_at = now_utc()

    def list_blogs(self) -> list[dict[str, Any]]:
        with session_scope(self.session_factory) as session:
            statement, _ = self._blog_select()
            rows = session.execute(statement.order_by(BlogModel.blog_id.asc(), BlogModel.id.asc())).all()
            return [self._row_blog_payload(row) for row in rows]

    def list_blogs_catalog(
        self,
        *,
        page: int = 1,
        page_size: int = BLOG_CATALOG_DEFAULT_PAGE_SIZE,
        site: str | None = None,
        url: str | None = None,
        status: str | None = None,
        statuses: str | None = None,
        q: str | None = None,
        sort: str = BLOG_CATALOG_DEFAULT_SORT,
        has_title: bool | str | None = None,
        has_icon: bool | str | None = None,
        min_connections: int | None = None,
    ) -> dict[str, Any]:
        query = normalize_blog_catalog_query(
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
        )
        with session_scope(self.session_factory) as session:
            statement, metrics = self._blog_select()
            if query["site"] is not None:
                pattern = f"%{query['site']}%"
                statement = statement.where(
                    or_(BlogModel.title.ilike(pattern), BlogModel.domain.ilike(pattern))
                )
            if query["url"] is not None:
                pattern = f"%{query['url']}%"
                statement = statement.where(
                    or_(BlogModel.url.ilike(pattern), BlogModel.normalized_url.ilike(pattern))
                )
            if query["statuses"] is not None:
                statement = statement.where(
                    func.upper(cast(BlogModel.crawl_status, String)).in_(tuple(query["statuses"]))
                )
            elif query["status"] is not None:
                statement = statement.where(
                    func.upper(cast(BlogModel.crawl_status, String)) == query["status"]
                )
            if query["q"] is not None:
                pattern = f"%{query['q']}%"
                statement = statement.where(
                    or_(
                        BlogModel.title.ilike(pattern),
                        BlogModel.domain.ilike(pattern),
                        BlogModel.url.ilike(pattern),
                    )
                )
            if query["has_title"] is True:
                statement = statement.where(
                    func.coalesce(func.nullif(BlogModel.title, ""), func.nullif(BlogModel.domain, "")).is_not(None)
                )
            if query["has_icon"] is True:
                statement = statement.where(
                    or_(
                        and_(BlogModel.icon_url.is_not(None), BlogModel.icon_url != ""),
                        BlogModel.url.like("http://%"),
                        BlogModel.url.like("https://%"),
                    )
                )
            if query["min_connections"] > 0:
                statement = statement.where(metrics["connection_count"] >= query["min_connections"])

            if query["sort"] == "recent_activity":
                statement = statement.order_by(
                    metrics["activity_at"].desc(),
                    metrics["connection_count"].desc(),
                    BlogModel.blog_id.desc(),
                    BlogModel.id.desc(),
                )
            elif query["sort"] == "connections":
                statement = statement.order_by(
                    metrics["connection_count"].desc(),
                    metrics["activity_at"].desc(),
                    BlogModel.blog_id.desc(),
                    BlogModel.id.desc(),
                )
            elif query["sort"] == "recently_discovered":
                statement = statement.order_by(BlogModel.created_at.desc(), BlogModel.blog_id.desc(), BlogModel.id.desc())
            elif query["sort"] == "id_asc":
                statement = statement.order_by(BlogModel.blog_id.asc(), BlogModel.id.asc())
            elif query["sort"] == "random":
                statement = statement.order_by(func.random())
            else:
                statement = statement.order_by(BlogModel.blog_id.desc(), BlogModel.id.desc())

            total_items = int(session.scalar(select(func.count()).select_from(statement.subquery())) or 0)
            total_pages = ceil(total_items / query["page_size"]) if total_items else 0
            effective_page = 1 if total_pages == 0 else min(query["page"], total_pages)
            offset = (effective_page - 1) * query["page_size"]
            rows = session.execute(statement.limit(query["page_size"]).offset(offset)).all()
            return _catalog_response(
                items=[self._row_blog_payload(row) for row in rows],
                page=effective_page,
                page_size=query["page_size"],
                total_items=total_items,
                filters={
                    "q": query["q"],
                    "site": query["site"],
                    "url": query["url"],
                    "status": query["status"],
                    "statuses": query["statuses"],
                    "sort": query["sort"],
                    "has_title": query["has_title"],
                    "has_icon": query["has_icon"],
                    "min_connections": query["min_connections"],
                },
            )

    def list_blog_labeling_candidates(
        self,
        *,
        page: int = 1,
        page_size: int = BLOG_LABELING_DEFAULT_PAGE_SIZE,
        q: str | None = None,
        label: str | None = None,
        labeled: bool | str | None = None,
        sort: str = BLOG_LABELING_DEFAULT_SORT,
    ) -> dict[str, Any]:
        query = normalize_blog_labeling_query(
            page=page,
            page_size=page_size,
            q=q,
            label=label,
            labeled=labeled,
            sort=sort,
        )
        with session_scope(self.session_factory) as session:
            statement, metrics = self._blog_labeling_select()
            statement = statement.where(BlogModel.crawl_status == CrawlStatus.FINISHED)
            if query["q"] is not None:
                pattern = f"%{query['q']}%"
                statement = statement.where(
                    or_(
                        BlogModel.title.ilike(pattern),
                        BlogModel.domain.ilike(pattern),
                        BlogModel.url.ilike(pattern),
                        BlogModel.normalized_url.ilike(pattern),
                    )
                )
            if query["label"] is not None:
                statement = statement.where(
                    BlogModel.blog_id.in_(
                        select(BlogLabelAssignmentModel.blog_id)
                        .join(BlogLabelTagModel, BlogLabelTagModel.id == BlogLabelAssignmentModel.tag_id)
                        .where(BlogLabelTagModel.slug == query["label"])
                    )
                )
            if query["labeled"] is True:
                statement = statement.where(metrics["latest_labeled_at"].is_not(None))
            elif query["labeled"] is False:
                statement = statement.where(metrics["latest_labeled_at"].is_(None))

            if query["sort"] == "recent_activity":
                statement = statement.order_by(
                    metrics["activity_at"].desc(),
                    BlogModel.blog_id.desc(),
                    BlogModel.id.desc(),
                )
            elif query["sort"] == "recently_labeled":
                statement = statement.order_by(
                    metrics["latest_labeled_at"].desc().nullslast(),
                    BlogModel.blog_id.desc(),
                    BlogModel.id.desc(),
                )
            else:
                statement = statement.order_by(BlogModel.blog_id.desc(), BlogModel.id.desc())

            total_items = int(session.scalar(select(func.count()).select_from(statement.subquery())) or 0)
            total_pages = ceil(total_items / query["page_size"]) if total_items else 0
            effective_page = 1 if total_pages == 0 else min(query["page"], total_pages)
            offset = (effective_page - 1) * query["page_size"]
            rows = session.execute(statement.limit(query["page_size"]).offset(offset)).all()
            blog_ids = [int(_business_blog_id(row[0])) for row in rows]
            label_rows = []
            if blog_ids:
                label_rows = session.execute(
                    select(BlogLabelAssignmentModel, BlogLabelTagModel)
                    .join(BlogLabelTagModel, BlogLabelTagModel.id == BlogLabelAssignmentModel.tag_id)
                    .where(BlogLabelAssignmentModel.blog_id.in_(blog_ids))
                    .order_by(BlogLabelAssignmentModel.blog_id.asc(), BlogLabelTagModel.name.asc())
                ).all()
            labels_by_blog: dict[int, list[dict[str, Any]]] = {blog_id: [] for blog_id in blog_ids}
            for assignment, tag in label_rows:
                labels_by_blog.setdefault(int(assignment.blog_id), []).append(
                    {
                        **_blog_label_tag_payload(tag),
                        "labeled_at": _iso(assignment.labeled_at),
                    }
                )
            available_tags = [
                _blog_label_tag_payload(tag)
                for tag in session.scalars(select(BlogLabelTagModel).order_by(BlogLabelTagModel.name.asc())).all()
            ]
            return _catalog_response(
                items=[
                    _blog_labeling_payload(
                        row,
                        labels=labels_by_blog.get(int(_business_blog_id(row[0])), []),
                        last_labeled_at=row.last_labeled_at,
                    )
                    for row in rows
                ],
                page=effective_page,
                page_size=query["page_size"],
                total_items=total_items,
                filters={
                    "q": query["q"],
                    "label": query["label"],
                    "labeled": query["labeled"],
                    "sort": query["sort"],
                },
            ) | {"available_tags": available_tags}

    def list_blog_label_tags(self) -> list[dict[str, Any]]:
        with session_scope(self.session_factory) as session:
            rows = session.scalars(select(BlogLabelTagModel).order_by(BlogLabelTagModel.name.asc())).all()
            return [_blog_label_tag_payload(row) for row in rows]

    def export_blog_label_training_csv(self) -> str:
        with session_scope(self.session_factory) as session:
            rows = session.execute(
                select(
                    BlogModel.url,
                    BlogModel.title,
                    BlogLabelTagModel.name.label("label_name"),
                )
                .join(BlogLabelAssignmentModel, BlogLabelAssignmentModel.blog_id == BlogModel.blog_id)
                .join(BlogLabelTagModel, BlogLabelTagModel.id == BlogLabelAssignmentModel.tag_id)
                .where(BlogModel.crawl_status == CrawlStatus.FINISHED)
                .order_by(BlogModel.blog_id.asc(), BlogLabelTagModel.name.asc())
            ).all()

        output = StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(["url", "title", "label"])
        for row in rows:
            writer.writerow([str(row.url), row.title or "", str(row.label_name)])
        return output.getvalue()

    def create_blog_label_tag(self, *, name: str) -> dict[str, Any]:
        normalized_name = _normalize_catalog_text(name)
        if normalized_name is None:
            raise ValueError("Unsupported blog label name")
        slug = slugify_blog_label(normalized_name)
        with session_scope(self.session_factory) as session:
            existing = session.scalar(select(BlogLabelTagModel).where(BlogLabelTagModel.slug == slug))
            if existing is not None:
                return _blog_label_tag_payload(existing)
            timestamp = now_utc()
            tag = BlogLabelTagModel(
                name=normalized_name,
                slug=slug,
                created_at=timestamp,
                updated_at=timestamp,
            )
            session.add(tag)
            session.flush()
            return _blog_label_tag_payload(tag)

    def replace_blog_link_labels(self, *, blog_id: int, tag_ids: list[int]) -> dict[str, Any]:
        unique_tag_ids = sorted({int(tag_id) for tag_id in tag_ids})
        with session_scope(self.session_factory) as session:
            blog = self._get_blog_by_business_id(session, blog_id)
            if blog is None:
                raise BlogLabelingNotFoundError("blog_not_found")
            if blog.crawl_status != CrawlStatus.FINISHED:
                raise BlogLabelingConflictError("blog_labeling_requires_finished_blog")
            resolved_blog_id = int(_business_blog_id(blog))
            tags = []
            if unique_tag_ids:
                tags = session.scalars(
                    select(BlogLabelTagModel).where(BlogLabelTagModel.id.in_(unique_tag_ids))
                ).all()
                if len(tags) != len(unique_tag_ids):
                    raise ValueError("blog_label_tag_not_found")
            existing_rows = session.scalars(
                select(BlogLabelAssignmentModel).where(BlogLabelAssignmentModel.blog_id == resolved_blog_id)
            )
            timestamp = now_utc()
            existing_by_tag = {int(row.tag_id): row for row in existing_rows}
            for tag_id, assignment in list(existing_by_tag.items()):
                if tag_id not in unique_tag_ids:
                    session.delete(assignment)
            for tag in tags:
                assignment = existing_by_tag.get(int(tag.id))
                if assignment is not None:
                    assignment.labeled_at = timestamp
                    assignment.updated_at = timestamp
                    continue
                session.add(
                    BlogLabelAssignmentModel(
                        blog_id=resolved_blog_id,
                        tag_id=int(tag.id),
                        labeled_at=timestamp,
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )
            session.flush()
            refreshed = session.execute(
                select(BlogLabelAssignmentModel, BlogLabelTagModel)
                .join(BlogLabelTagModel, BlogLabelTagModel.id == BlogLabelAssignmentModel.tag_id)
                .where(BlogLabelAssignmentModel.blog_id == resolved_blog_id)
                .order_by(BlogLabelTagModel.name.asc())
            ).all()
            labels = [
                {
                    **_blog_label_tag_payload(tag),
                    "labeled_at": _iso(assignment.labeled_at),
                }
                for assignment, tag in refreshed
            ]
            return {
                "blog_id": resolved_blog_id,
                "labels": labels,
                "label_slugs": [label["slug"] for label in labels],
                "last_labeled_at": _iso(timestamp if labels else None),
                "is_labeled": len(labels) > 0,
            }

    def get_blog(self, blog_id: int) -> dict[str, Any] | None:
        with session_scope(self.session_factory) as session:
            statement, _ = self._blog_select()
            row = session.execute(statement.where(BlogModel.blog_id == blog_id)).first()
            return self._row_blog_payload(row) if row is not None else None

    def get_blog_detail(self, blog_id: int) -> dict[str, Any] | None:
        with session_scope(self.session_factory) as session:
            statement, _ = self._blog_select()
            blog_row = session.execute(statement.where(BlogModel.blog_id == blog_id)).first()
            if blog_row is None:
                return None
            outgoing_edges = session.scalars(
                select(EdgeModel).where(EdgeModel.from_blog_id == blog_id).order_by(EdgeModel.id.asc())
            ).all()
            incoming_edges = session.scalars(
                select(EdgeModel).where(EdgeModel.to_blog_id == blog_id).order_by(EdgeModel.id.asc())
            ).all()

            def relation_payload(edge: EdgeModel, *, neighbor_id: int) -> dict[str, Any]:
                neighbor = self._get_blog_by_business_id(session, neighbor_id)
                return {
                    **_edge_payload(edge),
                    "neighbor_blog": _neighbor_payload(neighbor),
                }

            direct_related_ids = {
                int(edge.from_blog_id) for edge in incoming_edges
            } | {int(edge.to_blog_id) for edge in outgoing_edges}
            direct_outgoing_ids = {int(edge.to_blog_id) for edge in outgoing_edges}
            recommendation_map = collect_friends_of_friends_candidates(
                session,
                blog_id=blog_id,
                direct_outgoing_ids=direct_outgoing_ids,
                excluded_blog_ids=direct_related_ids,
            )

            recommended_rows: list[dict[str, Any]] = []
            if recommendation_map:
                recommended_statement, _ = self._blog_select()
                recommended_blog_rows = session.execute(
                    recommended_statement.where(BlogModel.blog_id.in_(recommendation_map.keys()))
                ).all()
                recommended_by_id = {
                    int(_business_blog_id(row[0])): row for row in recommended_blog_rows
                }
                via_blog_ids = {via_id for via_ids in recommendation_map.values() for via_id in via_ids}
                via_blogs = {
                    int(_business_blog_id(blog_model)): blog_model
                    for blog_model in session.scalars(
                        select(BlogModel).where(BlogModel.blog_id.in_(via_blog_ids))
                    ).all()
                }
                for candidate_id, via_ids in sorted(
                    recommendation_map.items(),
                    key=lambda item: (-len(item[1]), item[0]),
                ):
                    candidate_row = recommended_by_id.get(candidate_id)
                    if candidate_row is None:
                        continue
                    recommended_rows.append(
                        _recommended_blog_payload(
                            blog=candidate_row[0],
                            via_blogs=[via_blogs[via_id] for via_id in sorted(via_ids) if via_id in via_blogs],
                            incoming_count=int(candidate_row.incoming_count or 0),
                            outgoing_count=int(candidate_row.outgoing_count or 0),
                            activity_at=candidate_row.activity_at,
                            identity_complete=bool(candidate_row.identity_complete),
                        )
                    )

            return {
                **self._row_blog_payload(blog_row),
                "incoming_edges": [
                    relation_payload(edge, neighbor_id=int(edge.from_blog_id)) for edge in incoming_edges
                ],
                "outgoing_edges": [
                    relation_payload(edge, neighbor_id=int(edge.to_blog_id)) for edge in outgoing_edges
                ],
                "recommended_blogs": recommended_rows,
            }

    def list_edges(self) -> list[dict[str, Any]]:
        with session_scope(self.session_factory) as session:
            rows = session.scalars(select(EdgeModel).order_by(EdgeModel.id.asc())).all()
            return [_edge_payload(row) for row in rows]

    def list_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        return []

    def stats(self) -> dict[str, Any]:
        with session_scope(self.session_factory) as session:
            rows = session.execute(
                select(BlogModel.crawl_status, func.count()).group_by(BlogModel.crawl_status)
            ).all()
            status_counts = {str(status.value): int(count) for status, count in rows}
            total_blogs = int(session.scalar(select(func.count()).select_from(BlogModel)) or 0)
            total_edges = int(session.scalar(select(func.count()).select_from(EdgeModel)) or 0)
            average_friend_links = float(session.scalar(select(func.avg(BlogModel.friend_links_count))) or 0.0)
            return {
                "total_blogs": total_blogs,
                "total_edges": total_edges,
                "average_friend_links": average_friend_links,
                "status_counts": status_counts,
                "pending_tasks": int(status_counts.get(CrawlStatus.WAITING.value, 0)),
                "processing_tasks": int(status_counts.get(CrawlStatus.PROCESSING.value, 0)),
                "failed_tasks": int(status_counts.get(CrawlStatus.FAILED.value, 0)),
                "finished_tasks": int(status_counts.get(CrawlStatus.FINISHED.value, 0)),
            }

    def get_filter_stats_by_chain_order(self) -> dict[str, Any]:
        settings = self._decision_scan_settings()
        decision_chain = build_url_decision_chain(settings)
        with session_scope(self.session_factory) as session:
            total_raw = int(session.scalar(select(func.count()).select_from(RawDiscoveredUrlModel)) or 0)
            grouped_rows = session.execute(
                select(RawDiscoveredUrlModel.status, func.count()).group_by(RawDiscoveredUrlModel.status)
            ).all()
        counts_by_status = {str(status): int(count) for status, count in grouped_rows}
        remaining = total_raw
        by_filter_reason: dict[str, int] = {"raw": total_raw}
        for status in decision_chain.ordered_statuses():
            remaining -= counts_by_status.get(status, 0)
            by_filter_reason[status] = max(remaining, 0)
        return {"by_filter_reason": by_filter_reason}

    def create_url_refilter_run(self, *, crawler_was_running: bool = False) -> dict[str, Any]:
        with session_scope(self.session_factory) as session:
            run = UrlRefilterRunModel(
                status="PENDING",
                filter_chain_version=_filter_chain_version(self._decision_scan_settings()),
                crawler_was_running=crawler_was_running,
                backup_path=None,
                total_count=0,
                scanned_count=0,
                unchanged_count=0,
                activated_count=0,
                deactivated_count=0,
                retagged_count=0,
                last_raw_url_id=None,
                started_at=None,
                completed_at=None,
                error_message=None,
                created_at=now_utc(),
                updated_at=now_utc(),
            )
            session.add(run)
            session.flush()
            return _url_refilter_run_payload(run)

    def append_url_refilter_run_event(self, *, run_id: int, message: str) -> dict[str, Any]:
        with session_scope(self.session_factory) as session:
            run = session.get(UrlRefilterRunModel, run_id)
            if run is None:
                raise ValueError("url_refilter_run_not_found")
            event = self._append_url_refilter_run_event_in_session(session, run_id=run_id, message=message)
            run.updated_at = now_utc()
            return _url_refilter_run_event_payload(event)

    def mark_url_refilter_run_failed(self, *, run_id: int, error_message: str) -> dict[str, Any]:
        with session_scope(self.session_factory) as session:
            run = session.get(UrlRefilterRunModel, run_id)
            if run is None:
                raise ValueError("url_refilter_run_not_found")
            completed_at = now_utc()
            run.status = "FAILED"
            run.error_message = error_message
            run.completed_at = completed_at
            run.updated_at = completed_at
            self._append_url_refilter_run_event_in_session(
                session,
                run_id=run_id,
                message=f"重新过滤失败：{error_message}",
            )
            return _url_refilter_run_payload(run)

    def execute_url_refilter_run(self, *, run_id: int) -> dict[str, Any]:
        settings = self._decision_scan_settings()
        decision_chain = build_url_decision_chain(settings)
        started_at = now_utc()
        try:
            with session_scope(self.session_factory) as session:
                run = session.get(UrlRefilterRunModel, run_id)
                if run is None:
                    raise ValueError("url_refilter_run_not_found")
                run.status = "RUNNING"
                run.started_at = started_at
                run.completed_at = None
                run.error_message = None
                run.filter_chain_version = _filter_chain_version(settings)
                run.total_count = int(session.scalar(select(func.count()).select_from(RawDiscoveredUrlModel)) or 0)
                run.scanned_count = 0
                run.unchanged_count = 0
                run.activated_count = 0
                run.deactivated_count = 0
                run.retagged_count = 0
                run.last_raw_url_id = None
                run.updated_at = started_at
                self._append_url_refilter_run_event_in_session(session, run_id=run_id, message="备份中")

            backup_path = self._backup_sqlite_database()

            with session_scope(self.session_factory) as session:
                run = session.get(UrlRefilterRunModel, run_id)
                if run is None:
                    raise ValueError("url_refilter_run_not_found")
                run.backup_path = backup_path
                run.updated_at = now_utc()
                self._append_url_refilter_run_event_in_session(
                    session,
                    run_id=run_id,
                    message=f"备份完成，文件保存在 {backup_path}",
                )
                self._append_url_refilter_run_event_in_session(
                    session,
                    run_id=run_id,
                    message="开始按过滤链重新扫描原始URL表",
                )

            scanned_count = 0
            unchanged_count = 0
            activated_count = 0
            deactivated_count = 0
            retagged_count = 0
            last_raw_url_id = 0
            source_domain_cache: dict[int, str] = {}
            cursor = 0
            batch_size = 1000

            while True:
                with session_scope(self.session_factory) as session:
                    run = session.get(UrlRefilterRunModel, run_id)
                    if run is None:
                        raise ValueError("url_refilter_run_not_found")
                    raws = session.scalars(
                        select(RawDiscoveredUrlModel)
                        .where(RawDiscoveredUrlModel.id > cursor)
                        .order_by(RawDiscoveredUrlModel.id.asc())
                        .limit(batch_size)
                    ).all()
                    if not raws:
                        completed_at = now_utc()
                        run.status = "SUCCEEDED"
                        run.scanned_count = scanned_count
                        run.unchanged_count = unchanged_count
                        run.activated_count = activated_count
                        run.deactivated_count = deactivated_count
                        run.retagged_count = retagged_count
                        run.last_raw_url_id = last_raw_url_id or None
                        run.completed_at = completed_at
                        run.updated_at = completed_at
                        self._append_url_refilter_run_event_in_session(
                            session,
                            run_id=run_id,
                            message=(
                                "重新过滤完成："
                                f"scanned={scanned_count}, unchanged={unchanged_count}, "
                                f"activated={activated_count}, deactivated={deactivated_count}, "
                                f"retagged={retagged_count}"
                            ),
                        )
                        return _url_refilter_run_payload(run)

                    for raw in raws:
                        last_raw_url_id = int(raw.id)
                        source_blog_id = int(raw.source_blog_id)
                        source_domain = source_domain_cache.get(source_blog_id)
                        if source_domain is None:
                            source_blog = self._get_blog_by_business_id(session, source_blog_id)
                            source_domain = source_blog.domain if source_blog is not None else ""
                            source_domain_cache[source_blog_id] = source_domain

                        decision = decision_chain.evaluate(
                            UrlCandidateContext(
                                source_blog_id=source_blog_id,
                                source_domain=source_domain,
                                normalized_url=raw.normalized_url,
                            )
                        )
                        new_status = decision.status or "success"
                        old_status = str(raw.status)
                        if new_status == old_status:
                            unchanged_count += 1
                        else:
                            raw.status = new_status
                            raw.updated_at = now_utc()
                            if old_status != "success" and new_status == "success":
                                self._handle_refilter_activated_success(session, raw=raw)
                                activated_count += 1
                            elif old_status == "success" and new_status != "success":
                                self._handle_refilter_deactivated_success(session, raw=raw)
                                deactivated_count += 1
                            else:
                                retagged_count += 1
                        scanned_count += 1
                        cursor = int(raw.id)

                    run.scanned_count = scanned_count
                    run.unchanged_count = unchanged_count
                    run.activated_count = activated_count
                    run.deactivated_count = deactivated_count
                    run.retagged_count = retagged_count
                    run.last_raw_url_id = last_raw_url_id
                    run.updated_at = now_utc()
                    if scanned_count % 10_000 == 0 or scanned_count == int(run.total_count):
                        self._append_url_refilter_run_event_in_session(
                            session,
                            run_id=run_id,
                            message=(
                                f"当前扫描原始URL进度 {scanned_count}/{int(run.total_count)}，"
                                f"当前记录id={last_raw_url_id}"
                            ),
                        )
        except Exception as exc:
            self.mark_url_refilter_run_failed(run_id=run_id, error_message=str(exc))
            raise

    def get_latest_url_refilter_run(self) -> dict[str, Any] | None:
        with session_scope(self.session_factory) as session:
            run = session.scalar(select(UrlRefilterRunModel).order_by(UrlRefilterRunModel.id.desc()).limit(1))
            return _url_refilter_run_payload(run) if run is not None else None

    def list_url_refilter_run_events(self, run_id: int) -> list[dict[str, Any]]:
        with session_scope(self.session_factory) as session:
            rows = session.scalars(
                select(UrlRefilterRunEventModel)
                .where(UrlRefilterRunEventModel.run_id == run_id)
                .order_by(UrlRefilterRunEventModel.id.asc())
            ).all()
            return [_url_refilter_run_event_payload(row) for row in rows]

    def create_blog_dedup_scan_run(self, *, crawler_was_running: bool = False) -> dict[str, Any]:
        started_at = now_utc()
        settings = self._decision_scan_settings()
        with session_scope(self.session_factory) as session:
            total_count = int(session.scalar(select(func.count()).select_from(BlogModel)) or 0)
            run = BlogDedupScanRunModel(
                status="RUNNING",
                ruleset_version=_decision_scan_ruleset_version(settings),
                started_at=started_at,
                completed_at=None,
                duration_ms=0,
                total_count=total_count,
                scanned_count=0,
                removed_count=0,
                kept_count=0,
                crawler_was_running=crawler_was_running,
                crawler_restart_attempted=False,
                crawler_restart_succeeded=False,
                search_reindexed=False,
                error_message=None,
                created_at=started_at,
                updated_at=started_at,
            )
            session.add(run)
            session.flush()
            return _blog_dedup_scan_run_payload(run)

    def execute_blog_dedup_scan_run(self, *, run_id: int) -> dict[str, Any]:
        started_at = now_utc()
        settings = self._decision_scan_settings()
        decision_chain = build_url_decision_chain(settings)
        try:
            with session_scope(self.session_factory) as session:
                run = session.get(BlogDedupScanRunModel, run_id)
                if run is None:
                    raise ValueError("blog_dedup_scan_run_not_found")
                run.status = "RUNNING"
                run.started_at = run.started_at or started_at
                run.completed_at = None
                run.duration_ms = 0
                run.scanned_count = 0
                run.removed_count = 0
                run.kept_count = 0
                run.error_message = None
                run.updated_at = started_at
                blog_rows = session.execute(
                    select(
                        BlogModel.blog_id,
                        BlogModel.url,
                        BlogModel.domain,
                        BlogModel.identity_key,
                    )
                    .order_by(BlogModel.blog_id.asc(), BlogModel.id.asc())
                ).all()
                run.total_count = len(blog_rows)

            scanned_count = 0
            rejected_blog_count = 0
            for blog_row in blog_rows:
                with session_scope(self.session_factory) as session:
                    run = session.get(BlogDedupScanRunModel, run_id)
                    if run is None:
                        raise ValueError("blog_dedup_scan_run_not_found")
                    blog = self._get_blog_by_business_id(session, int(blog_row.blog_id))
                    if blog is None:
                        continue
                    decision = decision_chain.decide(
                        str(blog.url or ""),
                        "",
                        link_text=str(blog.domain or ""),
                        context_text="",
                    )
                    if not decision.accepted:
                        session.add(
                            BlogDedupScanRunItemModel(
                                run_id=int(run.id),
                                survivor_blog_id=None,
                                removed_blog_id=int(_business_blog_id(blog)),
                                survivor_identity_key=str(blog.identity_key or ""),
                                removed_url=str(blog.url or ""),
                                removed_normalized_url=str(blog.normalized_url or blog.url or ""),
                                removed_domain=str(blog.domain or ""),
                                reason_code=decision.reasons[0] if decision.reasons else "decision_rejected",
                                reason_codes=_dump_reason_codes(list(decision.reasons)),
                                survivor_selection_basis=(
                                    f"scanned_blog_id={int(_business_blog_id(blog))}, "
                                    f"decision_score={decision.score:.6f}"
                                ),
                                created_at=now_utc(),
                            )
                        )
                        self._delete_blog_graph(session, blog_id=int(_business_blog_id(blog)))
                        rejected_blog_count += 1

                    scanned_count += 1
                    completed_so_far = now_utc()
                    run.scanned_count = scanned_count
                    run.removed_count = rejected_blog_count
                    run.kept_count = max(run.total_count - rejected_blog_count, 0)
                    run.duration_ms = max(int((completed_so_far - started_at).total_seconds() * 1000), 0)
                    run.updated_at = completed_so_far

            with session_scope(self.session_factory) as session:
                run = session.get(BlogDedupScanRunModel, run_id)
                if run is None:
                    raise ValueError("blog_dedup_scan_run_not_found")
                completed_at = now_utc()
                final_blog_count = int(session.scalar(select(func.count()).select_from(BlogModel)) or 0)
                run.status = "SUCCEEDED"
                run.completed_at = completed_at
                run.duration_ms = max(int((completed_at - started_at).total_seconds() * 1000), 0)
                run.scanned_count = scanned_count
                run.removed_count = max(run.total_count - final_blog_count, 0)
                run.kept_count = final_blog_count
                run.updated_at = completed_at
                session.flush()
                return _blog_dedup_scan_run_payload(run)
        except Exception as exc:
            with session_scope(self.session_factory) as session:
                run = session.get(BlogDedupScanRunModel, run_id)
                if run is not None:
                    completed_at = now_utc()
                    run.status = "FAILED"
                    run.completed_at = completed_at
                    run.duration_ms = max(int((completed_at - started_at).total_seconds() * 1000), 0)
                    run.error_message = str(exc)
                    run.updated_at = completed_at
            raise

    def finalize_blog_dedup_scan_run(
        self,
        *,
        run_id: int,
        crawler_restart_attempted: bool,
        crawler_restart_succeeded: bool,
        search_reindexed: bool,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        with session_scope(self.session_factory) as session:
            run = session.get(BlogDedupScanRunModel, run_id)
            if run is None:
                raise ValueError("blog_dedup_scan_run_not_found")
            run.crawler_restart_attempted = crawler_restart_attempted
            run.crawler_restart_succeeded = crawler_restart_succeeded
            run.search_reindexed = search_reindexed
            if error_message:
                run.error_message = error_message
            run.updated_at = now_utc()
            session.flush()
            return _blog_dedup_scan_run_payload(run)

    def get_latest_blog_dedup_scan_run(self) -> dict[str, Any] | None:
        with session_scope(self.session_factory) as session:
            row = session.scalar(
                select(BlogDedupScanRunModel).order_by(BlogDedupScanRunModel.id.desc()).limit(1)
            )
            return _blog_dedup_scan_run_payload(row) if row is not None else None

    def list_blog_dedup_scan_run_items(self, run_id: int) -> list[dict[str, Any]]:
        with session_scope(self.session_factory) as session:
            rows = session.scalars(
                select(BlogDedupScanRunItemModel)
                .where(BlogDedupScanRunItemModel.run_id == run_id)
                .order_by(BlogDedupScanRunItemModel.id.asc())
            ).all()
            return [_blog_dedup_scan_run_item_payload(row) for row in rows]

    def reset(self) -> dict[str, Any]:
        with session_scope(self.session_factory) as session:
            blogs_deleted = int(session.scalar(select(func.count()).select_from(BlogModel)) or 0)
            edges_deleted = int(session.scalar(select(func.count()).select_from(EdgeModel)) or 0)
            requests_deleted = int(session.scalar(select(func.count()).select_from(IngestionRequestModel)) or 0)
            labels_deleted = int(session.scalar(select(func.count()).select_from(BlogLabelAssignmentModel)) or 0)
            tag_defs_deleted = int(session.scalar(select(func.count()).select_from(BlogLabelTagModel)) or 0)
            raw_urls_deleted = int(session.scalar(select(func.count()).select_from(RawDiscoveredUrlModel)) or 0)
            scan_items_deleted = int(
                session.scalar(select(func.count()).select_from(BlogDedupScanRunItemModel)) or 0
            )
            scan_runs_deleted = int(
                session.scalar(select(func.count()).select_from(BlogDedupScanRunModel)) or 0
            )
            refilter_events_deleted = int(
                session.scalar(select(func.count()).select_from(UrlRefilterRunEventModel)) or 0
            )
            refilter_runs_deleted = int(
                session.scalar(select(func.count()).select_from(UrlRefilterRunModel)) or 0
            )
            if self.dialect_name == "postgresql":
                session.execute(
                    text(
                        "TRUNCATE TABLE url_refilter_run_events, url_refilter_runs, "
                        "blog_dedup_scan_run_items, blog_dedup_scan_runs, "
                        "raw_discovered_urls, blog_label_assignments, blog_label_tags, "
                        "ingestion_requests, edges, blogs "
                        "RESTART IDENTITY CASCADE"
                    )
                )
            else:
                session.query(UrlRefilterRunEventModel).delete()
                session.query(UrlRefilterRunModel).delete()
                session.query(BlogDedupScanRunItemModel).delete()
                session.query(BlogDedupScanRunModel).delete()
                session.query(RawDiscoveredUrlModel).delete()
                session.query(BlogLabelAssignmentModel).delete()
                session.query(BlogLabelTagModel).delete()
                session.query(IngestionRequestModel).delete()
                session.query(EdgeModel).delete()
                session.query(BlogModel).delete()
            return {
                "ok": True,
                "blogs_deleted": blogs_deleted,
                "edges_deleted": edges_deleted,
                "logs_deleted": 0,
                "ingestion_requests_deleted": requests_deleted,
                "blog_link_labels_deleted": labels_deleted,
                "blog_label_tags_deleted": tag_defs_deleted,
                "raw_discovered_urls_deleted": raw_urls_deleted,
                "url_refilter_run_events_deleted": refilter_events_deleted,
                "url_refilter_runs_deleted": refilter_runs_deleted,
                "blog_dedup_scan_items_deleted": scan_items_deleted,
                "blog_dedup_scan_runs_deleted": scan_runs_deleted,
            }


class Repository(SQLAlchemyRepository):
    """Compatibility wrapper for test call sites that still pass a db path."""

    def __init__(self, db_path: Path, *, decision_settings: Settings | None = None) -> None:
        super().__init__(
            f"sqlite+pysqlite:///{db_path}",
            decision_settings=decision_settings,
            startup_schema_sync=True,
        )


def build_repository(
    *,
    db_path: Path,
    db_dsn: str | None = None,
    settings: Settings | None = None,
) -> RepositoryProtocol:
    """Build the configured repository implementation."""
    if db_dsn is not None:
        try:
            return SQLAlchemyRepository(db_dsn, decision_settings=settings, startup_schema_sync=False)
        except ModuleNotFoundError as exc:
            if exc.name != "psycopg":
                raise
    return Repository(db_path, decision_settings=settings)
