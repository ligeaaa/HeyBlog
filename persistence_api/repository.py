"""SQLAlchemy-backed persistence repository."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
from math import ceil
from pathlib import Path
from secrets import token_urlsafe
import re
import tempfile
from typing import Any
from typing import Callable
from typing import Protocol
from urllib.parse import urlparse

from sqlalchemy import and_
from sqlalchemy import case
from sqlalchemy import cast
from sqlalchemy import Float
from sqlalchemy import func
from sqlalchemy import Integer
from sqlalchemy import inspect
from sqlalchemy import ColumnElement
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy import String
from sqlalchemy import text
from sqlalchemy.orm import aliased
from sqlalchemy.orm import Session

from persistence_api.db import create_persistence_engine
from persistence_api.db import create_session_factory
from persistence_api.db import session_scope
from persistence_api.models import Base
from persistence_api.models import BlogLabelModel
from persistence_api.models import BlogLabelTagModel
from persistence_api.models import BlogInteractionModel
from persistence_api.models import BlogUserLabelModel
from persistence_api.models import BlogUserLabelSelectionModel
from persistence_api.models import BlogModel
from persistence_api.models import BlogDedupScanRunItemModel
from persistence_api.models import BlogDedupScanRunModel
from persistence_api.models import EdgeModel
from persistence_api.models import IngestionRequestModel
from persistence_api.models import RawDiscoveredUrlModel
from persistence_api.models import RecommendationImpressionModel
from persistence_api.models import RecommendationRequestModel
from persistence_api.models import SeedModel
from persistence_api.models import UserModel
from persistence_api.models import UserSessionModel
from persistence_api.recommendations import collect_friends_of_friends_candidates
from crawler.crawling.decisions.chain import build_url_decision_chain
from crawler.crawling.decisions.base import UrlCandidateContext
from crawler.crawling.normalization import IDENTITY_RULESET_VERSION
from crawler.crawling.normalization import BlogIdentityResolution
from crawler.crawling.normalization import normalize_url
from crawler.crawling.normalization import resolve_blog_identity
from shared.contracts.enums import CrawlStatus
from shared.config import Settings
from shared.observability import get_logger

BLOG_ACCEPTANCE_ACCEPTED = "ACCEPTED"
BLOG_ACCEPTANCE_UNKNOWN = "UNKNOWN"
BLOG_CATALOG_ALLOWED_STATUSES = frozenset({status.value for status in CrawlStatus})
BLOG_CATALOG_DEFAULT_PAGE_SIZE = 50
BLOG_CATALOG_MAX_PAGE_SIZE = 200
BLOG_CATALOG_DEFAULT_SORT = "id_desc"
BLOG_CATALOG_ALLOWED_SORTS = frozenset(
    {"id_asc", "id_desc", "recent_activity", "connections", "recently_discovered", "random"}
)
BLOG_CATALOG_ALLOWED_ACCEPTANCE_STATUSES = frozenset(
    {BLOG_ACCEPTANCE_ACCEPTED, BLOG_ACCEPTANCE_UNKNOWN, "REJECTED"}
)
INGESTION_PRIORITY_LIST_LIMIT = 20
BLOG_LABELING_DEFAULT_PAGE_SIZE = 50
BLOG_LABELING_MAX_PAGE_SIZE = 200
BLOG_LABELING_DEFAULT_SORT = "id_desc"
BLOG_LABELING_ALLOWED_SORTS = frozenset({"id_desc", "recent_activity", "recently_labeled"})
BLOG_LABELING_MODEL_FILTER_STATUS_PREFIX = "model:"
BLOG_LABELING_PARQUET_FILENAME = "blog-label-training.parquet"
BLOG_LABELING_PARQUET_BATCH_SIZE = 100
DEFAULT_BLOG_LABEL_TAGS = (
    (1, "blog"),
    (2, "company"),
    (3, "other"),
    (4, "unknown"),
    (5, "official"),
    (6, "government"),
)
BLOG_LABEL_NAME_TO_ID = {name: label_id for label_id, name in DEFAULT_BLOG_LABEL_TAGS}
BLOG_LABEL_ID_TO_NAME = {label_id: name for label_id, name in DEFAULT_BLOG_LABEL_TAGS}
RANDOM_BLOG_LABEL_SLUGS = frozenset({"blog", "company", "other", "unknown"})
BLOG_LABEL_BLOG_ID = BLOG_LABEL_NAME_TO_ID["blog"]
RAW_DISCOVERED_URL_DUPLICATE_STATUS = "rule:duplicate_url"
RAW_DISCOVERED_URL_SUCCESS_STATUS = "success"
RANDOM_RECOMMENDATION_SURFACE = "random_blog_page"
RANDOM_RECOMMENDATION_STRATEGY = "weighted_random"
RANDOM_RECOMMENDATION_STRATEGY_VERSION = "v1"
RECOMMENDATION_EVENT_TYPES = frozenset(
    {"click", "detail_open", "external_open", "label_select", "refresh", "dismiss", "copy_url"}
)
REPOSITORY_LOGGER_NAME = "heyblog.repository"
LOGGER = get_logger(REPOSITORY_LOGGER_NAME)
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
PASSWORD_MIN_LENGTH = 8
USER_SESSION_TTL_DAYS = 30
PASSWORD_HASH_ITERATIONS = 210_000


class BlogLabelingError(Exception):
    """Base error for blog labeling flows."""


class BlogLabelingNotFoundError(BlogLabelingError):
    """Raised when the target blog does not exist."""


class BlogLabelingConflictError(BlogLabelingError):
    """Raised when the target blog is not eligible for labeling."""


class UserAuthError(Exception):
    """Raised when a user auth request cannot be completed safely."""


def slugify_blog_label(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not normalized:
        raise ValueError("Unsupported blog label name")
    return normalized


def now_utc() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(UTC)


def _normalize_user_email(email: str) -> str:
    """Return canonical lowercase email text or raise for invalid input.

    Args:
        email: User-provided email address.

    Returns:
        Lowercase email address used for uniqueness and login.

    Raises:
        ValueError: Raised when the address is empty or syntactically invalid.
    """

    normalized = email.strip().lower()
    if not normalized or not EMAIL_PATTERN.match(normalized):
        raise ValueError("invalid_email")
    return normalized


def _validate_password(password: str) -> str:
    """Return a valid password or raise a stable validation error.

    Args:
        password: User-provided plaintext password.

    Returns:
        The original password when it satisfies the current policy.

    Raises:
        ValueError: Raised when the password is too short.
    """

    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError("password_too_short")
    return password


def _hash_password(password: str, *, salt: str | None = None) -> str:
    """Hash one plaintext password with PBKDF2-HMAC-SHA256.

    Args:
        password: Plaintext password accepted during registration.
        salt: Optional URL-safe salt text, mainly for deterministic tests.

    Returns:
        Versioned password hash string containing algorithm, iterations, salt,
        and derived key.
    """

    resolved_salt = salt or token_urlsafe(18)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        resolved_salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${resolved_salt}${digest}"


def _verify_password(password: str, password_hash: str) -> bool:
    """Return whether a plaintext password matches a stored hash.

    Args:
        password: Plaintext password supplied at login.
        password_hash: Stored versioned PBKDF2 hash string.

    Returns:
        True when the password matches; false for mismatches or unsupported
        hash formats.
    """

    try:
        algorithm, iterations_text, salt, expected_digest = password_hash.split("$", 3)
        iterations = int(iterations_text)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256" or iterations <= 0:
        return False
    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return hmac.compare_digest(actual_digest, expected_digest)


def _hash_session_token(token: str) -> str:
    """Return the database-safe hash for one bearer session token.

    Args:
        token: Raw bearer token that will be returned to the browser.

    Returns:
        SHA-256 hex digest used for lookup without storing the raw token.
    """

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _user_payload(model: UserModel) -> dict[str, Any]:
    """Return the public user profile payload.

    Args:
        model: User database row.

    Returns:
        JSON-serializable user summary safe for frontend profile screens.
    """

    return {
        "id": int(model.id),
        "email": model.email,
        "display_name": model.display_name,
        "created_at": _iso(model.created_at),
        "updated_at": _iso(model.updated_at),
    }


def _sortable_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _clean_event_text(value: str, *, field: str, max_length: int = 256) -> str:
    """Return a non-empty event text field or raise a stable validation error.

    Args:
        value: Raw event field value supplied by a caller.
        field: Field name included in the validation error.
        max_length: Maximum accepted character length.

    Returns:
        Trimmed field value.

    Raises:
        ValueError: Raised when the value is blank or too long.
    """

    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError(f"{field}_required")
    if len(cleaned) > max_length:
        raise ValueError(f"{field}_too_long")
    return cleaned


def _coerce_json_object(value: dict[str, Any] | None) -> dict[str, Any]:
    """Return a JSON object payload with unsupported values normalized by JSON.

    Args:
        value: Optional JSON-like mapping supplied by a caller.

    Returns:
        A JSON-serializable dictionary.

    Raises:
        ValueError: Raised when the mapping cannot be encoded as JSON.
    """

    if value is None:
        return {}
    try:
        return json.loads(json.dumps(value, ensure_ascii=True, default=str))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_json_attributes") from exc


def _parse_event_datetime(value: str | datetime | None) -> datetime | None:
    """Return an optional timezone-aware client event timestamp.

    Args:
        value: ISO datetime string, datetime instance, or `None`.

    Returns:
        Parsed datetime with UTC timezone when supplied.

    Raises:
        ValueError: Raised when the value cannot be parsed.
    """

    if value is None or isinstance(value, datetime):
        parsed = value
    else:
        normalized = str(value).strip()
        if not normalized:
            return None
        try:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("invalid_client_event_at") from exc
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


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


def _require_pyarrow() -> Any:
    """Import pyarrow lazily so non-export repository paths stay lightweight.

    Returns:
        Imported ``pyarrow`` module.

    Raises:
        RuntimeError: Raised when the parquet dependency is not installed.
    """

    try:
        import pyarrow as pa
    except ModuleNotFoundError as exc:
        raise RuntimeError("pyarrow_required_for_parquet_export") from exc
    return pa


def _require_pyarrow_parquet() -> Any:
    """Import pyarrow.parquet lazily for parquet file reads and writes.

    Returns:
        Imported ``pyarrow.parquet`` module.

    Raises:
        RuntimeError: Raised when the parquet dependency is not installed.
    """

    try:
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:
        raise RuntimeError("pyarrow_required_for_parquet_export") from exc
    return pq


def _blog_label_training_parquet_path(settings: Settings | None) -> Path:
    """Resolve the canonical parquet snapshot path for label training data.

    Args:
        settings: Repository settings carrying the configured export directory.

    Returns:
        Path to the training-label parquet file under the export directory.
    """

    export_dir = settings.export_dir if settings is not None else Path("data/exports")
    return export_dir / BLOG_LABELING_PARQUET_FILENAME


def _raw_url_is_labeling_eligible_status(status: str | None) -> bool:
    """Return whether one raw URL status belongs in the manual labeling pool.

    Args:
        status: Raw discovered URL status value.

    Returns:
        ``True`` for ``success`` and model-filter statuses.
    """

    return status == "success" or bool(status and status.startswith(BLOG_LABELING_MODEL_FILTER_STATUS_PREFIX))


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
    acceptance_status: str | None = BLOG_ACCEPTANCE_ACCEPTED,
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
    normalized_acceptance_status = _normalize_catalog_text(acceptance_status)
    if normalized_acceptance_status is not None:
        normalized_acceptance_status = normalized_acceptance_status.upper()
        if normalized_acceptance_status not in BLOG_CATALOG_ALLOWED_ACCEPTANCE_STATUSES:
            raise ValueError(f"Unsupported blog acceptance status: {normalized_acceptance_status}")

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
        "acceptance_status": normalized_acceptance_status,
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


def _count_selectable_rows(session: Session, selectable: Any) -> int:
    """Return a stable integer row count for one SQLAlchemy selectable."""
    return int(session.scalar(select(func.count()).select_from(selectable)) or 0)


def _resolve_page_window(*, total_items: int, page: int, page_size: int) -> tuple[int, int]:
    """Return the effective page number and row offset for one paginated query."""
    total_pages = ceil(total_items / page_size) if total_items else 0
    effective_page = 1 if total_pages == 0 else min(page, total_pages)
    return effective_page, (effective_page - 1) * page_size


def _execute_paginated_query(
    session: Session,
    statement: Any,
    *,
    page: int,
    page_size: int,
) -> tuple[list[Any], int, int]:
    """Execute one statement with shared count and page-window semantics."""
    total_items = _count_selectable_rows(session, statement.subquery())
    effective_page, offset = _resolve_page_window(
        total_items=total_items,
        page=page,
        page_size=page_size,
    )
    rows = session.execute(statement.limit(page_size).offset(offset)).all()
    return rows, total_items, effective_page


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
        if "feed_url" not in blog_columns:
            connection.execute(text("ALTER TABLE blogs ADD COLUMN feed_url TEXT"))
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
        if "seeds" not in existing_tables:
            if connection.dialect.name == "postgresql":
                connection.execute(
                    text(
                        "CREATE TABLE seeds ("
                        "id SERIAL PRIMARY KEY, "
                        "url TEXT NOT NULL, "
                        "normalized_url TEXT NOT NULL UNIQUE, "
                        "domain TEXT NOT NULL, "
                        "source_path TEXT, "
                        "source_row INTEGER, "
                        "blog_id INTEGER REFERENCES blogs(blog_id) ON DELETE SET NULL, "
                        "imported_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, "
                        "updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL)"
                    )
                )
            else:
                connection.execute(
                    text(
                        "CREATE TABLE seeds ("
                        "id INTEGER PRIMARY KEY, "
                        "url TEXT NOT NULL, "
                        "normalized_url TEXT NOT NULL UNIQUE, "
                        "domain TEXT NOT NULL, "
                        "source_path TEXT, "
                        "source_row INTEGER, "
                        "blog_id INTEGER REFERENCES blogs(blog_id) ON DELETE SET NULL, "
                        "imported_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, "
                        "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)"
                    )
                )
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_seeds_normalized_url ON seeds (normalized_url)"))
        if "blog_labels" not in existing_tables:
            if connection.dialect.name == "postgresql":
                connection.execute(
                    text(
                        "CREATE TABLE blog_labels ("
                        "normalized_url TEXT PRIMARY KEY, "
                        "title TEXT DEFAULT '' NOT NULL, "
                        "label_id JSONB NOT NULL DEFAULT '{}'::jsonb, "
                        "created_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, "
                        "updated_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL)"
                    )
                )
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_blog_labels_normalized_url "
                        "ON blog_labels (normalized_url)"
                    )
                )
            else:
                connection.execute(
                    text(
                        "CREATE TABLE blog_labels ("
                        "normalized_url TEXT PRIMARY KEY, "
                        "title TEXT DEFAULT '' NOT NULL, "
                        "label_id JSON NOT NULL DEFAULT '{}', "
                        "created_time DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, "
                        "updated_time DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)"
                    )
                )
            existing_tables.add("blog_labels")
        label_columns = {column["name"] for column in inspector.get_columns("blog_labels")}
        if "title" not in label_columns:
            connection.execute(text("ALTER TABLE blog_labels ADD COLUMN title TEXT DEFAULT '' NOT NULL"))
        if "blog_labels_userlabel" not in existing_tables:
            if connection.dialect.name == "postgresql":
                connection.execute(
                    text(
                        "CREATE TABLE blog_labels_userlabel ("
                        "normalized_url TEXT PRIMARY KEY, "
                        "title TEXT DEFAULT '' NOT NULL, "
                        "label_id JSONB NOT NULL DEFAULT '{}'::jsonb, "
                        "created_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, "
                        "updated_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL)"
                    )
                )
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_blog_labels_userlabel_normalized_url "
                        "ON blog_labels_userlabel (normalized_url)"
                    )
                )
            else:
                connection.execute(
                    text(
                        "CREATE TABLE blog_labels_userlabel ("
                        "normalized_url TEXT PRIMARY KEY, "
                        "title TEXT DEFAULT '' NOT NULL, "
                        "label_id JSON NOT NULL DEFAULT '{}', "
                        "created_time DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, "
                        "updated_time DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)"
                    )
                )
            existing_tables.add("blog_labels_userlabel")
        user_label_columns = {column["name"] for column in inspector.get_columns("blog_labels_userlabel")}
        if "title" not in user_label_columns:
            connection.execute(text("ALTER TABLE blog_labels_userlabel ADD COLUMN title TEXT DEFAULT '' NOT NULL"))
        if "users" not in existing_tables:
            connection.execute(
                text(
                    "CREATE TABLE users ("
                    "id INTEGER PRIMARY KEY, "
                    "email TEXT NOT NULL UNIQUE, "
                    "password_hash TEXT NOT NULL, "
                    "display_name TEXT DEFAULT '' NOT NULL, "
                    "created_at "
                    + ("TIMESTAMP WITH TIME ZONE" if connection.dialect.name == "postgresql" else "DATETIME")
                    + " DEFAULT CURRENT_TIMESTAMP NOT NULL, "
                    "updated_at "
                    + ("TIMESTAMP WITH TIME ZONE" if connection.dialect.name == "postgresql" else "DATETIME")
                    + " DEFAULT CURRENT_TIMESTAMP NOT NULL)"
                )
            )
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_users_email ON users (email)"))
            existing_tables.add("users")
        if "user_sessions" not in existing_tables:
            connection.execute(
                text(
                    "CREATE TABLE user_sessions ("
                    "id INTEGER PRIMARY KEY, "
                    "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                    "token_hash TEXT NOT NULL UNIQUE, "
                    "created_at "
                    + ("TIMESTAMP WITH TIME ZONE" if connection.dialect.name == "postgresql" else "DATETIME")
                    + " DEFAULT CURRENT_TIMESTAMP NOT NULL, "
                    "expires_at "
                    + ("TIMESTAMP WITH TIME ZONE" if connection.dialect.name == "postgresql" else "DATETIME")
                    + " NOT NULL, "
                    "revoked_at "
                    + ("TIMESTAMP WITH TIME ZONE" if connection.dialect.name == "postgresql" else "DATETIME")
                    + ")"
                )
            )
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_user_sessions_user_id ON user_sessions (user_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_user_sessions_token_hash ON user_sessions (token_hash)"))
            existing_tables.add("user_sessions")
        if "blog_user_label_selections" not in existing_tables:
            connection.execute(
                text(
                    "CREATE TABLE blog_user_label_selections ("
                    "id INTEGER PRIMARY KEY, "
                    "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                    "normalized_url TEXT NOT NULL, "
                    "label_id INTEGER NOT NULL, "
                    "created_at "
                    + ("TIMESTAMP WITH TIME ZONE" if connection.dialect.name == "postgresql" else "DATETIME")
                    + " DEFAULT CURRENT_TIMESTAMP NOT NULL, "
                    "updated_at "
                    + ("TIMESTAMP WITH TIME ZONE" if connection.dialect.name == "postgresql" else "DATETIME")
                    + " DEFAULT CURRENT_TIMESTAMP NOT NULL, "
                    "CONSTRAINT uq_user_label_selection_user_url UNIQUE (user_id, normalized_url))"
                )
            )
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_blog_user_label_selections_user_id ON blog_user_label_selections (user_id)")
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_blog_user_label_selections_normalized_url "
                    "ON blog_user_label_selections (normalized_url)"
                )
            )
            existing_tables.add("blog_user_label_selections")
        if "blog_interactions" in existing_tables:
            interaction_columns = {column["name"] for column in inspector.get_columns("blog_interactions")}
            if "entrance_kind" not in interaction_columns:
                connection.execute(
                    text("ALTER TABLE blog_interactions ADD COLUMN entrance_kind TEXT NOT NULL DEFAULT 'legacy_unknown'")
                )
                if connection.dialect.name == "postgresql":
                    connection.execute(text("ALTER TABLE blog_interactions ALTER COLUMN entrance_kind DROP DEFAULT"))
            if "entrance_url" not in interaction_columns:
                connection.execute(
                    text("ALTER TABLE blog_interactions ADD COLUMN entrance_url TEXT NOT NULL DEFAULT 'legacy_unknown'")
                )
                if connection.dialect.name == "postgresql":
                    connection.execute(text("ALTER TABLE blog_interactions ALTER COLUMN entrance_url DROP DEFAULT"))
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_blog_interactions_entrance_kind ON blog_interactions (entrance_kind)")
            )
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_blog_interactions_entrance_url ON blog_interactions (entrance_url)")
            )
        if "blog_label_tags" not in existing_tables:
            connection.execute(
                text(
                    "CREATE TABLE blog_label_tags ("
                    "id INTEGER PRIMARY KEY, "
                    "name TEXT NOT NULL, "
                    "slug TEXT NOT NULL UNIQUE, "
                    "created_at "
                    + ("TIMESTAMP WITH TIME ZONE" if connection.dialect.name == "postgresql" else "DATETIME")
                    + " DEFAULT CURRENT_TIMESTAMP NOT NULL, "
                    "updated_at "
                    + ("TIMESTAMP WITH TIME ZONE" if connection.dialect.name == "postgresql" else "DATETIME")
                    + " DEFAULT CURRENT_TIMESTAMP NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_blog_label_tags_slug "
                    "ON blog_label_tags (slug)"
                )
            )
            existing_tables.add("blog_label_tags")
        tag_columns = {column["name"] for column in inspector.get_columns("blog_label_tags")}
        if {"id", "name", "slug"}.issubset(tag_columns):
            for label_id, label_name in DEFAULT_BLOG_LABEL_TAGS:
                if connection.dialect.name == "postgresql":
                    connection.execute(
                        text(
                            "INSERT INTO blog_label_tags (id, name, slug) "
                            "VALUES (:id, :name, :slug) "
                            "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, slug = EXCLUDED.slug"
                        ),
                        {"id": label_id, "name": label_name, "slug": slugify_blog_label(label_name)},
                    )
                else:
                    connection.execute(
                        text(
                            "INSERT OR REPLACE INTO blog_label_tags (id, name, slug) "
                            "VALUES (:id, :name, :slug)"
                        ),
                        {"id": label_id, "name": label_name, "slug": slugify_blog_label(label_name)},
                    )
        migrated_label_rows: dict[str, dict[str, Any]] = {}
        if (
            "blog_link_labels" in existing_tables
        ):
            old_columns = {column["name"] for column in inspector.get_columns("blog_link_labels")}
            if {"blog_id", "label"}.issubset(old_columns):
                legacy_rows = connection.execute(
                    text("SELECT blog_id, label, labeled_at, created_at, updated_at FROM blog_link_labels")
                ).mappings().all()
                for row in legacy_rows:
                    normalized_url = connection.execute(
                        text("SELECT normalized_url FROM blogs WHERE blog_id = :blog_id"),
                        {"blog_id": row["blog_id"]},
                    ).scalar()
                    label_text = str(row["label"]).strip()
                    if normalized_url and label_text:
                        migrated = migrated_label_rows.setdefault(
                            str(normalized_url),
                            {"counts": {}, "created": row["created_at"], "updated": row["updated_at"]},
                        )
                        try:
                            label_key = str(_label_id_from_name(label_text))
                        except ValueError:
                            continue
                        migrated["counts"][label_key] = int(migrated["counts"].get(label_key, 0)) + 1
                        migrated["updated"] = row["updated_at"] or now_utc()
        if "blog_label_assignments" in existing_tables:
            assignment_rows = connection.execute(
                text(
                    "SELECT a.blog_id, a.tag_id, a.labeled_at, a.created_at, a.updated_at "
                    "FROM blog_label_assignments a ORDER BY a.id ASC"
                )
            ).mappings().all()
            for row in assignment_rows:
                normalized_url = None
                if "blog_label_subjects" in existing_tables:
                    normalized_url = connection.execute(
                        text("SELECT normalized_url FROM blog_label_subjects WHERE id = :subject_id"),
                        {"subject_id": row["blog_id"]},
                    ).scalar()
                if normalized_url is None:
                    normalized_url = connection.execute(
                        text("SELECT normalized_url FROM blogs WHERE blog_id = :blog_id"),
                        {"blog_id": row["blog_id"]},
                    ).scalar()
                if normalized_url is None and "raw_discovered_urls" in existing_tables:
                    normalized_url = connection.execute(
                        text("SELECT normalized_url FROM raw_discovered_urls WHERE id = :raw_id"),
                        {"raw_id": row["blog_id"]},
                    ).scalar()
                if normalized_url is None:
                    continue
                label_key = str(row["tag_id"])
                migrated = migrated_label_rows.setdefault(
                    str(normalized_url),
                    {"counts": {}, "created": row["created_at"], "updated": row["updated_at"]},
                )
                migrated["counts"][label_key] = int(migrated["counts"].get(label_key, 0)) + 1
                migrated["updated"] = row["updated_at"] or now_utc()
        for normalized_url, payload in migrated_label_rows.items():
            existing = connection.execute(
                text("SELECT label_id FROM blog_labels WHERE normalized_url = :normalized_url"),
                {"normalized_url": normalized_url},
            ).scalar()
            counts = _normalize_label_counts(json.loads(existing) if isinstance(existing, str) else existing)
            for label_key, count in payload["counts"].items():
                counts[str(label_key)] = int(counts.get(str(label_key), 0)) + int(count)
            if connection.dialect.name == "postgresql":
                connection.execute(
                    text(
                        "INSERT INTO blog_labels (normalized_url, title, label_id, created_time, updated_time) "
                        "VALUES (:normalized_url, :title, CAST(:label_id AS JSONB), :created_time, :updated_time) "
                        "ON CONFLICT (normalized_url) DO UPDATE "
                        "SET label_id = CAST(:label_id AS JSONB), updated_time = :updated_time"
                    ),
                    {
                        "normalized_url": normalized_url,
                        "title": "",
                        "label_id": json.dumps(counts),
                        "created_time": payload["created"] or now_utc(),
                        "updated_time": payload["updated"] or now_utc(),
                    },
                )
            else:
                connection.execute(
                    text(
                        "INSERT OR REPLACE INTO blog_labels "
                        "(normalized_url, title, label_id, created_time, updated_time) "
                        "VALUES (:normalized_url, :title, :label_id, :created_time, :updated_time)"
                    ),
                    {
                        "normalized_url": normalized_url,
                        "title": "",
                        "label_id": json.dumps(counts),
                        "created_time": payload["created"] or now_utc(),
                        "updated_time": payload["updated"] or now_utc(),
                    },
                )
        for obsolete_table in ("blog_label_assignments", "blog_label_subjects"):
            if obsolete_table in existing_tables:
                connection.execute(text(f"DROP TABLE IF EXISTS {obsolete_table} CASCADE"))
                existing_tables.discard(obsolete_table)
        if "raw_discovered_urls" in existing_tables:
            dialect_name = connection.dialect.name
            raw_url_columns = {column["name"] for column in inspector.get_columns("raw_discovered_urls")}
            if "accepted_by" not in raw_url_columns:
                connection.execute(text("ALTER TABLE raw_discovered_urls ADD COLUMN accepted_by TEXT"))
            existing_indexes = {index["name"] for index in inspector.get_indexes("raw_discovered_urls")}
            for index_name, columns in (
                ("ix_raw_discovered_urls_status_id", ("status", "id")),
                ("ix_raw_discovered_urls_status_normalized_url_id", ("status", "normalized_url", "id")),
                ("ix_raw_discovered_urls_normalized_url_id", ("normalized_url", "id")),
            ):
                if index_name in existing_indexes:
                    continue
                column_sql = ", ".join(columns)
                connection.execute(text(f"CREATE INDEX {index_name} ON raw_discovered_urls ({column_sql})"))
            if dialect_name == "postgresql":
                for foreign_key in inspector.get_foreign_keys("raw_discovered_urls"):
                    constrained_columns = set(foreign_key.get("constrained_columns") or [])
                    referred_table = foreign_key.get("referred_table")
                    constraint_name = str(foreign_key.get("name") or "")
                    if (
                        constraint_name
                        and referred_table == "blogs"
                        and constrained_columns == {"source_blog_id"}
                    ):
                        connection.execute(
                            text(f'ALTER TABLE raw_discovered_urls DROP CONSTRAINT IF EXISTS "{constraint_name}"')
                        )
        if "blogs" in existing_tables:
            blog_columns = {column["name"] for column in inspector.get_columns("blogs")}
            for column_name, ddl in (
                ("acceptance_status", "ALTER TABLE blogs ADD COLUMN acceptance_status TEXT NOT NULL DEFAULT 'UNKNOWN'"),
                ("accepted_by", "ALTER TABLE blogs ADD COLUMN accepted_by TEXT"),
                ("accepted_at", "ALTER TABLE blogs ADD COLUMN accepted_at TIMESTAMP"),
                ("crawl_error_kind", "ALTER TABLE blogs ADD COLUMN crawl_error_kind TEXT"),
                ("crawl_error_message", "ALTER TABLE blogs ADD COLUMN crawl_error_message TEXT"),
                ("last_crawl_attempt_at", "ALTER TABLE blogs ADD COLUMN last_crawl_attempt_at TIMESTAMP"),
                ("successful_crawl_at", "ALTER TABLE blogs ADD COLUMN successful_crawl_at TIMESTAMP"),
            ):
                if column_name not in blog_columns:
                    connection.execute(text(ddl))
            connection.execute(
                text(
                    "UPDATE blogs SET acceptance_status = 'ACCEPTED', "
                    "accepted_by = COALESCE(accepted_by, 'seed'), "
                    "accepted_at = COALESCE(accepted_at, created_at) "
                    "WHERE acceptance_status = 'UNKNOWN' "
                    "AND blog_id NOT IN (SELECT to_blog_id FROM edges)"
                )
            )
            connection.execute(
                text(
                    "UPDATE blogs SET acceptance_status = 'ACCEPTED', "
                    "accepted_by = COALESCE(accepted_by, 'graph'), "
                    "accepted_at = COALESCE(accepted_at, created_at) "
                    "WHERE acceptance_status = 'UNKNOWN' "
                    "AND blog_id IN (SELECT from_blog_id FROM edges UNION SELECT to_blog_id FROM edges)"
                )
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

def _resolved_blog_title(model: BlogModel) -> str:
    title = (model.title or "").strip()
    if title:
        return title
    return model.domain


def _resolved_blog_icon_url(model: BlogModel) -> str | None:
    icon_url = (model.icon_url or "").strip()
    if icon_url:
        return icon_url
    return None


@dataclass(frozen=True, slots=True)
class _BlogPayloadView:
    """Hold one resolved blog view and expose the payload slices used by the repository."""

    model: BlogModel
    blog_id: int
    title: str
    icon_url: str | None

    @classmethod
    def from_model(cls, model: BlogModel | None) -> _BlogPayloadView | None:
        """Return a resolved blog view for one model, or ``None`` when absent."""
        if model is None:
            return None
        return cls(
            model=model,
            blog_id=int(_business_blog_id(model)),
            title=_resolved_blog_title(model),
            icon_url=_resolved_blog_icon_url(model),
        )

    def as_blog_payload(
        self,
        *,
        incoming_count: int = 0,
        outgoing_count: int = 0,
        activity_at: datetime | None = None,
        identity_complete: bool | None = None,
    ) -> dict[str, Any]:
        """Return the full blog payload with optional metric overrides."""
        resolved_incoming_count = int(incoming_count)
        resolved_outgoing_count = int(outgoing_count)
        return {
            "id": self.blog_id,
            "blog_id": self.blog_id,
            "url": self.model.url,
            "normalized_url": self.model.normalized_url,
            "identity_key": self.model.identity_key,
            "identity_reason_codes": _load_reason_codes(self.model.identity_reason_codes),
            "identity_ruleset_version": self.model.identity_ruleset_version,
            "domain": self.model.domain,
            "email": self.model.email,
            "feed_url": self.model.feed_url,
            "title": self.title,
            "icon_url": self.icon_url,
            "status_code": self.model.status_code,
            "acceptance_status": self.model.acceptance_status,
            "accepted_by": self.model.accepted_by,
            "accepted_at": _iso(self.model.accepted_at),
            "crawl_error_kind": self.model.crawl_error_kind,
            "crawl_error_message": self.model.crawl_error_message,
            "last_crawl_attempt_at": _iso(self.model.last_crawl_attempt_at),
            "successful_crawl_at": _iso(self.model.successful_crawl_at),
            "crawl_status": self.model.crawl_status.value,
            "friend_links_count": int(self.model.friend_links_count),
            "last_crawled_at": _iso(self.model.last_crawled_at),
            "created_at": _iso(self.model.created_at),
            "updated_at": _iso(self.model.updated_at),
            "incoming_count": resolved_incoming_count,
            "outgoing_count": resolved_outgoing_count,
            "connection_count": resolved_incoming_count + resolved_outgoing_count,
            "activity_at": _iso(activity_at or self.model.last_crawled_at or self.model.updated_at),
            "identity_complete": bool(
                identity_complete
                if identity_complete is not None
                else (bool(self.title) and bool(self.icon_url))
            ),
        }

    def as_neighbor_payload(self) -> dict[str, Any]:
        """Return the compact blog payload used for neighbor references."""
        return {
            "id": self.blog_id,
            "blog_id": self.blog_id,
            "domain": self.model.domain,
            "title": self.title,
            "icon_url": self.icon_url,
        }

    def as_public_summary_payload(self) -> dict[str, Any]:
        """Return the public blog summary payload used by ingestion summaries."""
        return {
            "id": self.blog_id,
            "blog_id": self.blog_id,
            "url": self.model.url,
            "normalized_url": self.model.normalized_url,
            "domain": self.model.domain,
            "title": self.title,
            "icon_url": self.icon_url,
            "crawl_status": self.model.crawl_status.value,
        }


@dataclass(frozen=True, slots=True)
class _IngestionRequestPayloadView:
    """Hold one ingestion request plus its related blogs and expose output slices."""

    model: IngestionRequestModel
    seed_blog_view: _BlogPayloadView | None
    matched_blog_view: _BlogPayloadView | None

    @classmethod
    def from_model(
        cls,
        model: IngestionRequestModel,
        *,
        seed_blog: BlogModel | None = None,
        matched_blog: BlogModel | None = None,
    ) -> _IngestionRequestPayloadView:
        """Return the resolved request view for one ingestion request row."""
        return cls(
            model=model,
            seed_blog_view=_BlogPayloadView.from_model(seed_blog),
            matched_blog_view=_BlogPayloadView.from_model(matched_blog),
        )

    def _resolved_blog_view(self) -> _BlogPayloadView | None:
        """Return the matched blog when present, otherwise the seed blog."""
        return self.matched_blog_view or self.seed_blog_view

    def _resolved_blog_id(self) -> int | None:
        """Return the business id of the resolved blog used by public payloads."""
        resolved_blog_view = self._resolved_blog_view()
        return resolved_blog_view.blog_id if resolved_blog_view is not None else None

    def as_full_payload(self) -> dict[str, Any]:
        """Return the full ingestion request payload used by private flows."""
        resolved_blog_view = self._resolved_blog_view()
        return {
            "id": int(self.model.id),
            "request_id": int(self.model.id),
            "requested_url": self.model.requested_url,
            "normalized_url": self.model.normalized_url,
            "identity_key": self.model.identity_key,
            "identity_reason_codes": _load_reason_codes(self.model.identity_reason_codes),
            "identity_ruleset_version": self.model.identity_ruleset_version,
            "email": self.model.requester_email,
            "status": self.model.status,
            "priority": int(self.model.priority),
            "seed_blog_id": int(self.model.seed_blog_id) if self.model.seed_blog_id is not None else None,
            "matched_blog_id": int(self.model.matched_blog_id) if self.model.matched_blog_id is not None else None,
            "blog_id": self._resolved_blog_id(),
            "request_token": self.model.request_token,
            "expires_at": _iso(self.model.expires_at),
            "error_message": self.model.error_message,
            "created_at": _iso(self.model.created_at),
            "updated_at": _iso(self.model.updated_at),
            "seed_blog": self.seed_blog_view.as_blog_payload() if self.seed_blog_view is not None else None,
            "matched_blog": self.matched_blog_view.as_blog_payload() if self.matched_blog_view is not None else None,
            "blog": resolved_blog_view.as_blog_payload() if resolved_blog_view is not None else None,
        }

    def as_priority_payload(self) -> dict[str, Any]:
        """Return the public priority-list payload with private fields removed."""
        resolved_blog_view = self._resolved_blog_view()
        return {
            "request_id": int(self.model.id),
            "requested_url": self.model.requested_url,
            "normalized_url": self.model.normalized_url,
            "status": self.model.status,
            "seed_blog_id": int(self.model.seed_blog_id) if self.model.seed_blog_id is not None else None,
            "matched_blog_id": int(self.model.matched_blog_id) if self.model.matched_blog_id is not None else None,
            "blog_id": self._resolved_blog_id(),
            "error_message": self.model.error_message,
            "created_at": _iso(self.model.created_at),
            "updated_at": _iso(self.model.updated_at),
            "blog": (
                resolved_blog_view.as_public_summary_payload()
                if resolved_blog_view is not None
                else None
            ),
        }


def _edge_payload(model: EdgeModel) -> dict[str, Any]:
    return {
        "id": int(model.id),
        "from_blog_id": int(model.from_blog_id),
        "to_blog_id": int(model.to_blog_id),
        "link_url_raw": model.link_url_raw,
        "link_text": model.link_text,
        "discovered_at": _iso(model.discovered_at),
    }


def _seed_payload(model: SeedModel) -> dict[str, Any]:
    """Serialize one durable seed row for crawler bootstrap.

    Args:
        model: Seed ORM row to serialize.

    Returns:
        Plain JSON-compatible seed payload.
    """

    return {
        "id": int(model.id),
        "url": str(model.url),
        "normalized_url": str(model.normalized_url),
        "domain": str(model.domain),
        "source_path": model.source_path,
        "source_row": model.source_row,
        "blog_id": model.blog_id,
        "imported_at": _iso(model.imported_at),
        "updated_at": _iso(model.updated_at),
    }


def _ingestion_request_payload(
    model: IngestionRequestModel,
    *,
    seed_blog: BlogModel | None = None,
    matched_blog: BlogModel | None = None,
) -> dict[str, Any]:
    return _IngestionRequestPayloadView.from_model(
        model,
        seed_blog=seed_blog,
        matched_blog=matched_blog,
    ).as_full_payload()


def _priority_ingestion_request_payload(
    model: IngestionRequestModel,
    *,
    seed_blog: BlogModel | None = None,
    matched_blog: BlogModel | None = None,
) -> dict[str, Any]:
    return _IngestionRequestPayloadView.from_model(
        model,
        seed_blog=seed_blog,
        matched_blog=matched_blog,
    ).as_priority_payload()


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


def _normalize_label_counts(value: Any) -> dict[str, int]:
    """Return a clean label-count mapping with string IDs and positive counts."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, int] = {}
    for key, count in value.items():
        key_text = str(key).strip()
        if not key_text:
            continue
        try:
            label_id = int(key_text)
        except ValueError:
            continue
        if label_id <= 0:
            continue
        try:
            resolved_count = int(count)
        except (TypeError, ValueError):
            continue
        if resolved_count > 0:
            normalized[str(label_id)] = resolved_count
    return normalized


def _label_counts_from_tag_ids(tag_ids: list[int] | None) -> dict[str, int]:
    """Return one-count label mapping from the legacy tag-id list payload."""
    return _normalize_label_counts({str(tag_id): 1 for tag_id in (tag_ids or [])})


def _json_label_count_expr(label_json: Any, label_id: int) -> Any:
    """Return one JSON label-count SQL expression coerced to an integer."""
    return cast(func.coalesce(label_json[str(label_id)].as_integer(), 0), Integer)


def _non_blog_label_count_expr(label_json: Any) -> Any:
    """Return the SQL sum of known non-blog label counts for one JSON field."""
    counts = [
        _json_label_count_expr(label_json, label_id)
        for label_id, label_name in DEFAULT_BLOG_LABEL_TAGS
        if label_id != BLOG_LABEL_BLOG_ID and label_name != "blog"
    ]
    total = counts[0]
    for count in counts[1:]:
        total = total + count
    return total


def _label_payloads_from_counts(
    label_counts: dict[str, int],
    *,
    labeled_at: datetime | None,
    label_names: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    """Return compatibility label payloads from stored label-count data."""
    resolved_names = label_names or BLOG_LABEL_ID_TO_NAME
    return [
        {
            "id": int(label_id) if label_id.isdigit() else label_id,
            "name": resolved_names.get(int(label_id), label_id) if label_id.isdigit() else label_id,
            "slug": slugify_blog_label(resolved_names.get(int(label_id), label_id)) if label_id.isdigit() else label_id,
            "count": int(count),
            "labeled_at": _iso(labeled_at),
        }
        for label_id, count in sorted(label_counts.items(), key=lambda item: item[0])
    ]


def _label_tag_payload_from_id(label_id: int, *, label_name: str | None = None) -> dict[str, Any]:
    """Return a compatibility tag payload for one label definition."""
    label_text = label_name or BLOG_LABEL_ID_TO_NAME.get(label_id, str(label_id))
    return {
        "id": label_id,
        "name": label_text,
        "slug": slugify_blog_label(label_text),
        "created_at": None,
        "updated_at": None,
    }


def _label_tag_payload_from_model(tag: BlogLabelTagModel) -> dict[str, Any]:
    """Return the API payload for a persisted label definition."""
    return {
        "id": int(tag.id),
        "name": tag.name,
        "slug": tag.slug,
        "created_at": _iso(tag.created_at),
        "updated_at": _iso(tag.updated_at),
    }


def _blog_label_names_by_id(session: Session) -> dict[int, str]:
    """Load label definition names keyed by label id."""
    return {
        int(tag.id): tag.name
        for tag in session.scalars(select(BlogLabelTagModel)).all()
    } | BLOG_LABEL_ID_TO_NAME


def _blog_label_tag_payloads(session: Session) -> list[dict[str, Any]]:
    """Load all persisted label definitions in stable id order."""
    return [
        _label_tag_payload_from_model(tag)
        for tag in session.scalars(select(BlogLabelTagModel).order_by(BlogLabelTagModel.id.asc())).all()
    ]


def _label_id_from_name_in_session(session: Session, name: str) -> int:
    """Resolve a label name, slug, or numeric id through persisted definitions."""
    normalized_name = _normalize_catalog_text(name)
    if normalized_name is None:
        raise ValueError("Unsupported blog label name")
    slug = slugify_blog_label(normalized_name)
    tag = session.scalar(select(BlogLabelTagModel).where(BlogLabelTagModel.slug == slug).limit(1))
    if tag is not None:
        return int(tag.id)
    try:
        label_id = int(normalized_name)
    except ValueError as exc:
        raise ValueError("Unsupported blog label name") from exc
    if label_id <= 0:
        raise ValueError("Unsupported blog label name")
    return label_id


def _label_id_from_name(name: str) -> int:
    """Resolve an admin label name into the stored numeric label ID."""
    normalized_name = _normalize_catalog_text(name)
    if normalized_name is None:
        raise ValueError("Unsupported blog label name")
    if normalized_name in BLOG_LABEL_NAME_TO_ID:
        return BLOG_LABEL_NAME_TO_ID[normalized_name]
    try:
        label_id = int(normalized_name)
    except ValueError as exc:
        raise ValueError("Unsupported blog label name") from exc
    if label_id <= 0:
        raise ValueError("Unsupported blog label name")
    return label_id


@dataclass(frozen=True, slots=True)
class _BlogLabelStateView:
    """Hold one blog's resolved label facts and expose the shared state payload."""

    blog_id: int
    label_counts: dict[str, int]
    last_labeled_at: datetime | None
    label_names: dict[int, str] = field(default_factory=dict)

    @classmethod
    def empty(
        cls,
        *,
        blog_id: int,
        last_labeled_at: datetime | None = None,
        label_names: dict[int, str] | None = None,
    ) -> _BlogLabelStateView:
        """Return an empty label-state view for one blog."""
        return cls(blog_id=blog_id, label_counts={}, last_labeled_at=last_labeled_at, label_names=label_names or {})

    @classmethod
    def from_assignment_rows(
        cls,
        *,
        blog_id: int,
        label_counts: dict[str, int],
        last_labeled_at: datetime | None = None,
        label_names: dict[int, str] | None = None,
    ) -> _BlogLabelStateView:
        """Return one label-state view built from a label-count mapping."""
        return cls(
            blog_id=blog_id,
            label_counts=_normalize_label_counts(label_counts),
            last_labeled_at=last_labeled_at,
            label_names=label_names or {},
        )

    def as_payload(self) -> dict[str, Any]:
        """Return the shared label-state payload used by labeling read/write flows."""
        labels = _label_payloads_from_counts(
            self.label_counts,
            labeled_at=self.last_labeled_at,
            label_names=self.label_names,
        )
        return {
            "blog_id": self.blog_id,
            "label_id": self.label_counts,
            "labels": labels,
            "label_slugs": [str(label["slug"]) for label in labels],
            "last_labeled_at": _iso(self.last_labeled_at),
            "is_labeled": len(self.label_counts) > 0,
        }


@dataclass(frozen=True, slots=True)
class _MaintenanceRunPayloadView:
    """Hold the shared lifecycle facts exposed by maintenance run summaries."""

    run_id: int
    status: str
    crawler_was_running: bool
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    created_at: datetime | None
    updated_at: datetime | None

    @classmethod
    def from_model(
        cls,
        model: BlogDedupScanRunModel,
    ) -> _MaintenanceRunPayloadView:
        """Return the shared lifecycle view for one maintenance run row."""
        return cls(
            run_id=int(model.id),
            status=str(model.status),
            crawler_was_running=bool(model.crawler_was_running),
            started_at=model.started_at,
            completed_at=model.completed_at,
            error_message=model.error_message,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def as_payload(self) -> dict[str, Any]:
        """Return the shared lifecycle payload used by maintenance run summaries."""
        return {
            "id": self.run_id,
            "status": self.status,
            "crawler_was_running": self.crawler_was_running,
            "started_at": _iso(self.started_at),
            "completed_at": _iso(self.completed_at),
            "error_message": self.error_message,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }


def _blog_dedup_scan_run_payload(model: BlogDedupScanRunModel) -> dict[str, Any]:
    run_view = _MaintenanceRunPayloadView.from_model(model)
    return run_view.as_payload() | {
        "ruleset_version": model.ruleset_version,
        "duration_ms": int(model.duration_ms),
        "total_count": int(model.total_count),
        "scanned_count": int(model.scanned_count),
        "removed_count": int(model.removed_count),
        "kept_count": int(model.kept_count),
        "crawler_restart_attempted": bool(model.crawler_restart_attempted),
        "crawler_restart_succeeded": bool(model.crawler_restart_succeeded),
        "search_reindexed": bool(model.search_reindexed),
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


def _blog_labeling_payload(
    row: Any,
    *,
    label_state: _BlogLabelStateView,
) -> dict[str, Any]:
    blog = row[0]
    blog_view = _BlogPayloadView.from_model(blog)
    if blog_view is None:
        raise ValueError("blog_not_found")
    return {
        **blog_view.as_blog_payload(
            incoming_count=int(row.incoming_count or 0),
            outgoing_count=int(row.outgoing_count or 0),
            activity_at=row.activity_at,
            identity_complete=bool(row.identity_complete),
        ),
        **label_state.as_payload(),
    }


def _raw_blog_labeling_payload(
    row: Any,
    *,
    label_state: _BlogLabelStateView,
    display_title: str | None = None,
) -> dict[str, Any]:
    """Return labeling candidate payload from a raw URL plus optional blog row.

    Args:
        row: SQLAlchemy row containing raw URL fields and optional blog fields.
        label_state: Resolved labels for the candidate target id.
        display_title: Title resolved from persisted label data or blog data.

    Returns:
        Candidate payload compatible with the existing labeling UI.
    """

    target_id = int(row.target_id)
    url = str(row.normalized_url)
    return {
        "id": target_id,
        "blog_id": target_id,
        "url": str(row.blog_url or url),
        "normalized_url": url,
        "identity_key": str(row.identity_key or ""),
        "identity_reason_codes": _load_reason_codes(row.identity_reason_codes),
        "identity_ruleset_version": str(row.identity_ruleset_version or ""),
        "domain": str(row.blog_domain or normalize_url(url).domain),
        "email": row.email,
        "title": str(display_title if display_title is not None else row.title or ""),
        "icon_url": row.icon_url,
        "status_code": row.status_code,
        "crawl_status": row.crawl_status.value if row.crawl_status is not None else None,
        "friend_links_count": int(row.friend_links_count or 0),
        "last_crawled_at": _iso(row.last_crawled_at),
        "created_at": _iso(row.blog_created_at or row.raw_created_at),
        "updated_at": _iso(row.blog_updated_at or row.raw_updated_at),
        "incoming_count": int(row.incoming_count or 0),
        "outgoing_count": int(row.outgoing_count or 0),
        "connection_count": int(row.incoming_count or 0) + int(row.outgoing_count or 0),
        "activity_at": _iso(row.activity_at or row.blog_updated_at or row.raw_updated_at),
        "identity_complete": bool((row.title or "").strip() and (row.icon_url or "").strip()),
        **label_state.as_payload(),
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
    blog_view = _BlogPayloadView.from_model(blog)
    if blog_view is None:
        raise ValueError("blog_not_found")
    return {
        "blog": blog_view.as_blog_payload(
            incoming_count=incoming_count,
            outgoing_count=outgoing_count,
            activity_at=activity_at,
            identity_complete=identity_complete,
        ),
        "reason": "mutual_connection",
        "mutual_connection_count": len(via_blogs),
        "via_blogs": [
            via_blog_view.as_neighbor_payload()
            for via_blog in via_blogs
            if (via_blog_view := _BlogPayloadView.from_model(via_blog)) is not None
        ],
    }


DISCOVERY_SOURCE_LABELS = {
    "seed": "种子导入",
    "user": "用户手动添加",
    "rss": "RSS 判定",
    "model": "模型判定",
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
        feed_url: str | None = None,
        accepted_by: str | None = None,
        seed_source_path: str | None = None,
        seed_source_row: int | None = None,
    ) -> tuple[int, bool]: ...

    def list_seeds(self) -> list[dict[str, Any]]: ...

    def get_next_waiting_blog(self, *, include_priority: bool = True) -> dict[str, Any] | None: ...

    def get_next_priority_blog(self) -> dict[str, Any] | None: ...

    def create_ingestion_request(self, *, homepage_url: str, email: str) -> dict[str, Any]: ...

    def create_user_seed(self, *, homepage_url: str) -> dict[str, Any]: ...

    def register_user(self, *, email: str, password: str) -> dict[str, Any]: ...

    def login_user(self, *, email: str, password: str) -> dict[str, Any]: ...

    def get_user_by_session_token(self, *, token: str) -> dict[str, Any] | None: ...

    def revoke_user_session(self, *, token: str) -> bool: ...

    def list_user_label_selections(self, *, user_id: int, limit: int = 50) -> list[dict[str, Any]]: ...

    def count_user_label_selections(self, *, user_id: int) -> int: ...

    def get_ingestion_request(
        self,
        *,
        request_id: int,
        request_token: str,
    ) -> dict[str, Any] | None: ...

    def list_priority_ingestion_requests(self, *, limit: int = INGESTION_PRIORITY_LIST_LIMIT) -> list[dict[str, Any]]: ...

    def lookup_blog_candidates(self, *, url: str) -> dict[str, Any]: ...

    def find_blog_id_by_normalized_url(self, *, normalized_url: str) -> int | None: ...

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
        crawl_error_kind: str | None = None,
        crawl_error_message: str | None = None,
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

    def create_raw_discovered_url_record(
        self,
        *,
        source_blog_id: int,
        normalized_url: str,
        status: str,
    ) -> dict[str, Any]: ...

    def update_raw_discovered_url_status(
        self,
        *,
        record_id: int,
        status: str,
        accepted_by: str | None = None,
    ) -> None: ...

    def requeue_failed_blogs(self) -> dict[str, Any]: ...

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
        acceptance_status: str | None = BLOG_ACCEPTANCE_ACCEPTED,
    ) -> dict[str, Any]: ...

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
    ) -> dict[str, Any]: ...

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
        client_event_at: str | datetime | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def get_blog_recommendation_stats(self, blog_id: int) -> dict[str, Any] | None: ...

    def get_recommendation_strategy_stats(self) -> dict[str, Any]: ...

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

    def replace_blog_link_labels(
        self,
        *,
        blog_id: int,
        tag_ids: list[int] | None = None,
        label_id: dict[str, int] | None = None,
    ) -> dict[str, Any]: ...

    def increment_blog_user_label(
        self,
        *,
        blog_id: int,
        label: str,
        previous_label: str | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]: ...

    def ensure_labelable_raw_url_blogs(self) -> dict[str, int]: ...

    def get_labelable_blog_by_url(self, *, url: str) -> dict[str, Any] | None: ...

    def get_blog_label_training_parquet_status(self) -> dict[str, Any]: ...

    def sync_blog_label_training_parquet(self) -> dict[str, Any]: ...

    def rebuild_blog_label_training_parquet(self) -> dict[str, Any]: ...

    def export_blog_label_training_parquet(self) -> tuple[bytes, dict[str, Any]]: ...

    def get_blog(self, blog_id: int) -> dict[str, Any] | None: ...

    def get_blog_detail(self, blog_id: int) -> dict[str, Any] | None: ...

    def list_edges(self) -> list[dict[str, Any]]: ...

    def list_logs(self, limit: int = 100) -> list[dict[str, Any]]: ...

    def stats(self) -> dict[str, Any]: ...

    def get_filter_stats_by_chain_order(self) -> dict[str, Any]: ...

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

    def _get_blog_by_business_id(self, session: Session, blog_id: int) -> BlogModel | None:
        """Return one blog row by business ``blog_id``."""
        return session.scalar(select(BlogModel).where(BlogModel.blog_id == blog_id))

    def _ensure_schema(self) -> None:
        ensure_legacy_compat_schema(self.engine)

    def _blog_labeling_select(self) -> tuple[Any, dict[str, Any]]:
        statement, metrics = self._blog_select()
        latest_labeled_at = (
            select(
                BlogLabelModel.normalized_url.label("normalized_url"),
                BlogLabelModel.updated_time.label("last_labeled_at"),
            )
            .subquery()
        )
        statement = statement.outerjoin(
            latest_labeled_at,
            latest_labeled_at.c.normalized_url == BlogModel.normalized_url,
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
        blog_view = _BlogPayloadView.from_model(row[0])
        if blog_view is None:
            raise ValueError("blog_not_found")
        return blog_view.as_blog_payload(
            incoming_count=int(row.incoming_count or 0),
            outgoing_count=int(row.outgoing_count or 0),
            activity_at=row.activity_at,
            identity_complete=bool(row.identity_complete),
        )

    def _serialize_ingestion_request_payload(
        self,
        session: Session,
        request: IngestionRequestModel,
        *,
        serializer: Callable[..., dict[str, Any]],
    ) -> dict[str, Any]:
        """Resolve request blogs once and pass them to the chosen serializer."""
        seed_blog, matched_blog = self._resolve_ingestion_request_blogs(session, request)
        return serializer(request, seed_blog=seed_blog, matched_blog=matched_blog)

    def _serialize_ingestion_request_payloads(
        self,
        session: Session,
        requests: list[IngestionRequestModel],
        *,
        serializer: Callable[..., dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Resolve and serialize multiple ingestion requests using the shared serializer handoff."""
        return [
            self._serialize_ingestion_request_payload(
                session,
                request,
                serializer=serializer,
            )
            for request in requests
        ]

    def _resolve_ingestion_request_blogs(
        self,
        session: Session,
        request: IngestionRequestModel,
    ) -> tuple[BlogModel | None, BlogModel | None]:
        """Resolve the seed and matched blogs referenced by one ingestion request."""
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
        return seed_blog, matched_blog

    def _latest_row_payload(
        self,
        session: Session,
        *,
        statement: Any,
        serializer: Callable[[Any], dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Return the serialized payload for the latest matching row or ``None``."""
        row = session.scalar(statement)
        return serializer(row) if row is not None else None

    def _ordered_row_payloads(
        self,
        session: Session,
        *,
        statement: Any,
        serializer: Callable[[Any], dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return ordered row payloads for one scalar-select statement."""
        return [serializer(row) for row in session.scalars(statement).all()]

    def _blog_label_rows_by_url(
        self,
        session: Session,
        *,
        normalized_urls: list[str],
    ) -> dict[str, BlogLabelModel]:
        """Return URL-keyed label rows for the provided normalized URLs.

        Args:
            session: Active SQLAlchemy session.
            normalized_urls: Stable normalized URL keys to load labels.

        Returns:
            Mapping from normalized URL to its ``BlogLabelModel`` row.
        """

        if not normalized_urls:
            return {}
        rows = session.scalars(
            select(BlogLabelModel).where(BlogLabelModel.normalized_url.in_(normalized_urls))
        ).all()
        return {row.normalized_url: row for row in rows}

    def _ensure_blog_label_row(
        self,
        session: Session,
        *,
        normalized_url: str,
        title: str | None = None,
    ) -> BlogLabelModel:
        """Return the single-table label row for a normalized URL.

        Args:
            session: Active SQLAlchemy session.
            normalized_url: URL key that should persist independently of crawl
                run rows.
            title: Optional display title captured with the label state.

        Returns:
            Existing or newly-created ``BlogLabelModel``.
        """

        label_row = session.scalar(
            select(BlogLabelModel).where(BlogLabelModel.normalized_url == normalized_url)
        )
        if label_row is not None:
            clean_title = (title or "").strip()
            if clean_title:
                label_row.title = clean_title
            return label_row
        timestamp = now_utc()
        label_row = BlogLabelModel(
            normalized_url=normalized_url,
            title=(title or "").strip(),
            label_id={},
            created_time=timestamp,
            updated_time=timestamp,
        )
        session.add(label_row)
        session.flush()
        return label_row

    def _ensure_blog_user_label_row(
        self,
        session: Session,
        *,
        normalized_url: str,
        title: str | None = None,
    ) -> BlogUserLabelModel:
        """Return the random-page user-label row for a normalized URL.

        Args:
            session: Active SQLAlchemy session.
            normalized_url: Stable URL key that receives public label votes.
            title: Optional display title captured with the user vote.

        Returns:
            Existing or newly-created ``BlogUserLabelModel`` row.
        """

        label_row = session.scalar(
            select(BlogUserLabelModel).where(BlogUserLabelModel.normalized_url == normalized_url)
        )
        clean_title = (title or "").strip()
        if label_row is not None:
            if clean_title:
                label_row.title = clean_title
            return label_row
        timestamp = now_utc()
        label_row = BlogUserLabelModel(
            normalized_url=normalized_url,
            title=clean_title,
            label_id={},
            created_time=timestamp,
            updated_time=timestamp,
        )
        session.add(label_row)
        session.flush()
        return label_row

    def _random_blog_catalog_statement(self, statement: Any) -> Any:
        """Apply admin-label exclusion and user-feedback weighting to random catalog reads.

        Args:
            statement: Base blog catalog select with standard blog metrics.

        Returns:
            Statement ordered by the capped weighted random expression.
        """

        admin_non_blog = _non_blog_label_count_expr(BlogLabelModel.label_id)
        user_non_blog_count = _non_blog_label_count_expr(BlogUserLabelModel.label_id)
        random_weight = cast(10, Float) / cast(1 + user_non_blog_count, Float)
        return (
            statement.outerjoin(BlogLabelModel, BlogLabelModel.normalized_url == BlogModel.normalized_url)
            .outerjoin(BlogUserLabelModel, BlogUserLabelModel.normalized_url == BlogModel.normalized_url)
            .where(admin_non_blog == 0)
            .order_by((func.random() * random_weight).desc(), BlogModel.blog_id.desc(), BlogModel.id.desc())
        )

    def _require_model(
        self,
        session: Session,
        model_type: Any,
        primary_key: Any,
        *,
        not_found_error: str,
    ) -> Any:
        """Return one persisted model by primary key or raise the configured ``ValueError``."""
        model = session.get(model_type, primary_key)
        if model is None:
            raise ValueError(not_found_error)
        return model

    def _blog_detail_relation_payloads(
        self,
        session: Session,
        edges: list[EdgeModel],
        *,
        neighbor_id_getter: Callable[[EdgeModel], int],
    ) -> list[dict[str, Any]]:
        """Return ordered blog-detail edge payloads using the provided neighbor-id selector."""
        return [
            {
                **_edge_payload(edge),
                "neighbor_blog": (
                    blog_view.as_neighbor_payload()
                    if (
                        blog_view := _BlogPayloadView.from_model(
                            self._get_blog_by_business_id(session, neighbor_id_getter(edge))
                        )
                    )
                    is not None
                    else None
                ),
            }
            for edge in edges
        ]

    def _blog_discovery_path_payload(self, session: Session, blog: BlogModel) -> dict[str, Any]:
        """Return a compact discovery-path payload for one blog.

        Args:
            session: Active database session used for tracing raw discoveries.
            blog: Blog row being displayed on the detail page.

        Returns:
            Payload with discovery mode and ordered path steps from origin to
            target. Manual seed/user blogs return a single-step path.
        """

        path_reversed: list[dict[str, Any]] = []
        visited_blog_ids: set[int] = set()
        current_blog: BlogModel | None = blog
        while current_blog is not None:
            if current_blog is None:
                break
            current_blog_id = int(_business_blog_id(current_blog))
            if current_blog_id in visited_blog_ids:
                break
            visited_blog_ids.add(current_blog_id)
            accepted_by = str(current_blog.accepted_by or "").strip().lower()
            if accepted_by in {"seed", "user"}:
                path_reversed.append(self._discovery_path_step(current_blog, raw=None, edge=None))
                break
            incoming_edge = self._earliest_incoming_discovery_edge(session, current_blog_id)
            raw = (
                self._success_raw_for_edge(session, incoming_edge)
                if incoming_edge is not None
                else self._earliest_success_raw_for_blog(session, current_blog)
            )
            path_reversed.append(self._discovery_path_step(current_blog, raw=raw, edge=incoming_edge))
            source_blog_id = int(incoming_edge.from_blog_id) if incoming_edge is not None else (
                int(raw.source_blog_id) if raw is not None else None
            )
            if source_blog_id is None:
                break
            current_blog = self._get_blog_by_business_id(session, source_blog_id)

        path = list(reversed(path_reversed))
        origin_source = str(path[0].get("accepted_by") or path[0].get("raw_accepted_by") or "").strip().lower() if path else ""
        target_source = str(path[-1].get("accepted_by") or path[-1].get("raw_accepted_by") or "").strip().lower() if path else ""
        mode = "manual" if target_source in {"seed", "user"} and len(path) == 1 else "crawled"
        if origin_source in {"seed", "user"} and mode == "crawled":
            origin_label = DISCOVERY_SOURCE_LABELS.get(origin_source, origin_source)
        else:
            origin_label = "发现链路"
        return {
            "mode": mode,
            "origin_source": origin_source or None,
            "origin_label": origin_label,
            "target_source": target_source or None,
            "truncated": False,
            "steps": path,
        }

    def _earliest_incoming_discovery_edge(self, session: Session, blog_id: int) -> EdgeModel | None:
        """Return the earliest non-self incoming edge that discovered a blog."""

        return session.scalar(
            select(EdgeModel)
            .where(
                EdgeModel.to_blog_id == blog_id,
                EdgeModel.from_blog_id != blog_id,
            )
            .order_by(EdgeModel.discovered_at.asc(), EdgeModel.id.asc())
            .limit(1)
        )

    def _success_raw_for_edge(self, session: Session, edge: EdgeModel) -> RawDiscoveredUrlModel | None:
        """Return the successful raw discovery row that produced one edge when available."""

        candidate_urls = {
            str(edge.link_url_raw or ""),
            normalize_url(str(edge.link_url_raw or "")).normalized_url,
            resolve_blog_identity(str(edge.link_url_raw or "")).canonical_url,
        }
        return session.scalar(
            select(RawDiscoveredUrlModel)
            .where(
                RawDiscoveredUrlModel.source_blog_id == int(edge.from_blog_id),
                RawDiscoveredUrlModel.normalized_url.in_([url for url in candidate_urls if url]),
                RawDiscoveredUrlModel.status == RAW_DISCOVERED_URL_SUCCESS_STATUS,
            )
            .order_by(RawDiscoveredUrlModel.id.asc())
            .limit(1)
        )

    def _earliest_success_raw_for_blog(self, session: Session, blog: BlogModel) -> RawDiscoveredUrlModel | None:
        """Return the earliest successful raw discovery row for one blog."""

        candidate_urls = {str(blog.normalized_url or ""), str(blog.url or "")}
        identity = resolve_blog_identity(str(blog.url or blog.normalized_url or ""))
        candidate_urls.add(identity.canonical_url)
        normalized = normalize_url(str(blog.url or blog.normalized_url or ""))
        candidate_urls.add(normalized.normalized_url)
        return session.scalar(
            select(RawDiscoveredUrlModel)
            .where(
                RawDiscoveredUrlModel.normalized_url.in_([url for url in candidate_urls if url]),
                RawDiscoveredUrlModel.status == RAW_DISCOVERED_URL_SUCCESS_STATUS,
            )
            .order_by(RawDiscoveredUrlModel.id.asc())
            .limit(1)
        )

    def _discovery_path_step(
        self,
        blog: BlogModel,
        *,
        raw: RawDiscoveredUrlModel | None,
        edge: EdgeModel | None,
    ) -> dict[str, Any]:
        """Serialize one blog as a discovery path step."""

        blog_view = _BlogPayloadView.from_model(blog)
        accepted_by = str(blog.accepted_by or "").strip().lower() or None
        raw_accepted_by = str(raw.accepted_by or "").strip().lower() if raw is not None else None
        source = accepted_by or raw_accepted_by
        raw_source_blog_id = int(raw.source_blog_id) if raw is not None else (
            int(edge.from_blog_id) if edge is not None else None
        )
        discovered_at = _iso(raw.discovered_at) if raw is not None else (
            _iso(edge.discovered_at) if edge is not None else None
        )
        return {
            "blog": blog_view.as_neighbor_payload() if blog_view is not None else None,
            "blog_id": int(_business_blog_id(blog)),
            "url": str(blog.url or ""),
            "domain": str(blog.domain or ""),
            "accepted_by": accepted_by,
            "accepted_label": DISCOVERY_SOURCE_LABELS.get(str(source or ""), source),
            "raw_id": int(raw.id) if raw is not None else None,
            "raw_source_blog_id": raw_source_blog_id,
            "raw_accepted_by": raw_accepted_by or None,
            "discovered_at": discovered_at,
        }

    def _blog_relation_graph_payload(
        self,
        session: Session,
        *,
        blog: BlogModel,
        direction: str,
        depth: int = 2,
    ) -> dict[str, Any]:
        """Return a small directional relation graph around one blog.

        Args:
            session: Active database session.
            blog: Focus blog for the graph.
            direction: Either ``incoming`` for upstream sources or
                ``outgoing`` for downstream targets.
            depth: Number of graph layers to traverse.

        Returns:
            Payload with normalized graph nodes, directed edges, focus blog id,
            direction, and depth metadata.
        """

        focus_id = int(_business_blog_id(blog))
        node_ids: set[int] = {focus_id}
        edges_by_id: dict[int, EdgeModel] = {}
        frontier = {focus_id}
        for layer_index in range(depth):
            next_frontier: set[int] = set()
            for current_id in sorted(frontier):
                if direction == "incoming":
                    statement = (
                        select(EdgeModel)
                        .where(EdgeModel.to_blog_id == current_id, EdgeModel.from_blog_id != current_id)
                        .order_by(EdgeModel.discovered_at.asc(), EdgeModel.id.asc())
                    )
                else:
                    statement = (
                        select(EdgeModel)
                        .where(EdgeModel.from_blog_id == current_id, EdgeModel.to_blog_id != current_id)
                        .order_by(EdgeModel.discovered_at.asc(), EdgeModel.id.asc())
                    )
                layer_edges = session.scalars(statement).all()
                for edge in layer_edges:
                    edges_by_id[int(edge.id)] = edge
                    related_id = int(edge.from_blog_id) if direction == "incoming" else int(edge.to_blog_id)
                    if related_id not in node_ids:
                        next_frontier.add(related_id)
                    node_ids.add(related_id)
            frontier = next_frontier
            if not frontier:
                break

        blog_rows = session.execute(
            self._blog_select()[0].where(BlogModel.blog_id.in_(sorted(node_ids)))
        ).all()
        nodes_by_id: dict[int, dict[str, Any]] = {}
        for row in blog_rows:
            payload = self._row_blog_payload(row)
            nodes_by_id[int(payload["blog_id"])] = payload
        return {
            "direction": direction,
            "focus_blog_id": focus_id,
            "depth": depth,
            "nodes": [nodes_by_id[node_id] for node_id in sorted(node_ids) if node_id in nodes_by_id],
            "edges": [_edge_payload(edge) for edge in sorted(edges_by_id.values(), key=lambda item: int(item.id))],
        }

    def _recommended_blog_rows(
        self,
        session: Session,
        recommendation_map: dict[int, set[int]],
    ) -> list[dict[str, Any]]:
        """Return sorted recommended-blog payloads for one blog-detail response."""
        if not recommendation_map:
            return []

        statement, _ = self._blog_select()
        recommended_blog_rows = session.execute(
            statement.where(BlogModel.blog_id.in_(list(recommendation_map.keys())))
        ).all()
        recommended_by_id = {
            int(_business_blog_id(row[0])): row for row in recommended_blog_rows
        }
        via_blog_ids = {via_id for via_ids in recommendation_map.values() for via_id in via_ids}
        via_blogs = {
            int(_business_blog_id(blog_model)): blog_model
            for blog_model in session.scalars(select(BlogModel).where(BlogModel.blog_id.in_(via_blog_ids))).all()
        }

        recommended_rows: list[dict[str, Any]] = []
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
        return recommended_rows

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

    def _upsert_blog_in_session(
        self,
        session: Session,
        *,
        url: str,
        normalized_url: str,
        domain: str,
        email: str | None = None,
        feed_url: str | None = None,
        accepted_by: str | None = None,
        preferred_blog_id: int | None = None,
    ) -> tuple[BlogModel, bool]:
        """Create or update one blog row and initialize its business id.

        Args:
            session: Active SQLAlchemy session.
            url: Original URL to store.
            normalized_url: Normalized URL candidate.
            domain: Domain associated with the URL.
            email: Optional contact email to fill when the row is missing one.
            feed_url: Optional RSS/Atom feed URL discovered for the blog. Stored
                when present; an existing feed is never overwritten with ``None``.
            accepted_by: Optional acceptance source such as ``seed``, ``rss``,
                or ``model``. When present, the blog is durably accepted.
            preferred_blog_id: Preferred externally meaningful ``blogs.blog_id``.

        Returns:
            Tuple of ``(blog, inserted)``. ``blog.blog_id`` is initialized when
            a new row is inserted or an older row is still missing the value.
        """

        identity = resolve_blog_identity(url or normalized_url)
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
            if feed_url is not None and not (existing.feed_url or "").strip():
                existing.feed_url = feed_url
            if existing.acceptance_status != BLOG_ACCEPTANCE_ACCEPTED:
                existing.acceptance_status = BLOG_ACCEPTANCE_ACCEPTED
                existing.accepted_at = existing.accepted_at or now_utc()
            if accepted_by is not None:
                existing.accepted_by = accepted_by
                existing.accepted_at = existing.accepted_at or now_utc()
            existing.identity_key = identity.identity_key
            existing.identity_reason_codes = _dump_reason_codes(identity.reason_codes)
            existing.identity_ruleset_version = identity.ruleset_version
            if preferred_blog_id is not None and existing.blog_id is None:
                existing.blog_id = self._resolve_business_blog_id(
                    session,
                    preferred_blog_id=preferred_blog_id,
                    target_blog=existing,
                )
            existing.updated_at = now_utc()
            return existing, False

        blog = BlogModel(
            blog_id=None,
            url=stored_url,
            normalized_url=stored_url,
            identity_key=identity.identity_key,
            identity_reason_codes=_dump_reason_codes(identity.reason_codes),
            identity_ruleset_version=identity.ruleset_version,
            domain=stored_domain,
            email=email,
            feed_url=feed_url,
            acceptance_status=BLOG_ACCEPTANCE_ACCEPTED,
            accepted_by=accepted_by,
            accepted_at=now_utc(),
            crawl_status=CrawlStatus.WAITING,
            friend_links_count=0,
            created_at=now_utc(),
            updated_at=now_utc(),
        )
        session.add(blog)
        session.flush()
        blog.blog_id = self._resolve_business_blog_id(
            session,
            preferred_blog_id=preferred_blog_id,
            target_blog=blog,
        )
        session.flush()
        return blog, True

    def _resolve_business_blog_id(
        self,
        session: Session,
        *,
        preferred_blog_id: int | None,
        target_blog: BlogModel,
    ) -> int:
        """Return a unique business ``blog_id`` for one blog row.

        Args:
            session: Active SQLAlchemy session.
            preferred_blog_id: Externally meaningful ID to use first when free.
            target_blog: Blog row that will receive the returned business ID.

        Returns:
            A unique ``blogs.blog_id``. Raw-derived rows use
            ``raw_discovered_urls.id`` when that value is still available; if a
            legacy row already owns it, the function falls back to the normal
            monotonic business-ID space.
        """

        def is_available(candidate: int) -> bool:
            holder = session.scalar(select(BlogModel).where(BlogModel.blog_id == candidate))
            return holder is None or int(holder.id) == int(target_blog.id)

        if preferred_blog_id is not None and is_available(preferred_blog_id):
            return int(preferred_blog_id)

        fallback = int(target_blog.id)
        if is_available(fallback):
            return fallback

        max_blog_id = int(session.scalar(select(func.max(BlogModel.blog_id))) or 0)
        max_row_id = int(session.scalar(select(func.max(BlogModel.id))) or 0)
        candidate = max(max_blog_id, max_row_id) + 1
        while not is_available(candidate):
            candidate += 1
        return candidate

    def _ensure_edge_in_session(
        self,
        session: Session,
        *,
        from_blog_id: int,
        to_blog_id: int,
        link_url_raw: str,
        link_text: str | None,
    ) -> None:
        for pending in session.new:
            if not isinstance(pending, EdgeModel):
                continue
            if int(pending.from_blog_id) == int(from_blog_id) and int(pending.to_blog_id) == int(to_blog_id):
                return
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

    def _delete_blog_graph(self, session: Session, *, blog_id: int) -> None:
        """Delete one blog and its direct graph attachments safely.

        Args:
            session: Active database session used for the deletion.
            blog_id: Blog identifier that should be removed from persistence.

        Returns:
            ``None``. The blog, its edges, and dangling ingestion references
            are removed or cleared in place. URL-keyed label assignments are
            intentionally preserved across graph cleanup.
        """
        edge_ids = session.scalars(
            select(EdgeModel.id).where(
                or_(
                    EdgeModel.from_blog_id == blog_id,
                    EdgeModel.to_blog_id == blog_id,
                )
            )
        ).all()
        if edge_ids:
            session.query(EdgeModel).filter(EdgeModel.id.in_(edge_ids)).delete(synchronize_session=False)
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
        feed_url: str | None = None,
        accepted_by: str | None = None,
        seed_source_path: str | None = None,
        seed_source_row: int | None = None,
    ) -> tuple[int, bool]:
        with session_scope(self.session_factory) as session:
            blog, inserted = self._upsert_blog_in_session(
                session,
                url=url,
                normalized_url=normalized_url,
                domain=domain,
                email=email,
                feed_url=feed_url,
                accepted_by=accepted_by,
            )
            if accepted_by == "seed":
                self._upsert_seed_in_session(
                    session,
                    url=url,
                    normalized_url=str(blog.normalized_url),
                    domain=str(blog.domain),
                    blog_id=int(_business_blog_id(blog)),
                    source_path=seed_source_path,
                    source_row=seed_source_row,
                )
            return int(_business_blog_id(blog)), inserted

    def _upsert_seed_in_session(
        self,
        session: Session,
        *,
        url: str,
        normalized_url: str,
        domain: str,
        blog_id: int,
        source_path: str | None = None,
        source_row: int | None = None,
    ) -> SeedModel:
        """Create or refresh the durable seed row for one imported URL.

        Args:
            session: Active SQLAlchemy session that already contains the blog
                upsert for the same import.
            url: Original URL from the seed CSV row.
            normalized_url: Stored blog normalized URL after identity
                canonicalization.
            domain: Stored blog domain.
            blog_id: Business blog identifier linked from the seed row.
            source_path: Optional CSV path used for traceability.
            source_row: Optional one-based CSV data row number.

        Returns:
            The created or updated seed row.
        """

        imported_at = now_utc()
        seed = session.scalar(select(SeedModel).where(SeedModel.normalized_url == normalized_url))
        if seed is None:
            seed = SeedModel(
                url=url,
                normalized_url=normalized_url,
                domain=domain,
                source_path=source_path,
                source_row=source_row,
                blog_id=blog_id,
                imported_at=imported_at,
                updated_at=imported_at,
            )
            session.add(seed)
            session.flush()
            return seed

        seed.url = url
        seed.domain = domain
        seed.blog_id = blog_id
        seed.source_path = source_path
        seed.source_row = source_row
        seed.updated_at = imported_at
        return seed

    def list_seeds(self) -> list[dict[str, Any]]:
        """Return all durable seed rows in deterministic insertion order.

        Args:
            None.

        Returns:
            Seed payloads ordered by primary key for bootstrap replay.
        """

        with session_scope(self.session_factory) as session:
            return self._ordered_row_payloads(
                session,
                statement=select(SeedModel).order_by(SeedModel.id.asc()),
                serializer=_seed_payload,
            )

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
                existing_blog_view = _BlogPayloadView.from_model(existing_blog)
                return {
                    "status": INGESTION_REQUEST_STATUS_DEDUPED_EXISTING,
                    "blog_id": int(_business_blog_id(existing_blog)),
                    "matched_blog_id": int(_business_blog_id(existing_blog)),
                    "request_id": None,
                    "request_token": None,
                    "blog": existing_blog_view.as_blog_payload() if existing_blog_view is not None else None,
                }

            existing_request = self._oldest_ingestion_request(
                session,
                filters=(IngestionRequestModel.identity_key == identity_key,),
                statuses=tuple(ACTIVE_INGESTION_REQUEST_STATUSES),
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
                return self._serialize_ingestion_request_payload(
                    session,
                    existing_request,
                    serializer=_ingestion_request_payload,
                )

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
                    acceptance_status=BLOG_ACCEPTANCE_ACCEPTED,
                    accepted_by="seed",
                    accepted_at=now_utc(),
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
            return self._serialize_ingestion_request_payload(
                session,
                request,
                serializer=_ingestion_request_payload,
            )

    def create_user_seed(self, *, homepage_url: str) -> dict[str, Any]:
        """Accept one user-submitted URL as a crawler seed after rule checks.

        Args:
            homepage_url: Complete blog homepage URL provided by a public user.

        Returns:
            Payload describing the accepted blog and whether a row was inserted.

        Raises:
            ValueError: Raised when URL normalization fails or deterministic
                rule filters reject the URL.
        """

        requested_url, normalized_url, domain, _identity_key, _reason_codes, _ruleset_version = normalize_homepage_url(
            homepage_url
        )
        settings = self._decision_scan_settings()
        decision_chain = build_url_decision_chain(settings)
        candidate = UrlCandidateContext(
            source_blog_id=0,
            source_domain="",
            normalized_url=normalized_url,
            link_text="user",
            context_text="user-submitted seed",
        )
        for rule_filter in decision_chain.rule_filters:
            decision = rule_filter.apply(candidate)
            if not decision.accepted:
                raise ValueError(str(decision.status or "rule_filter_rejected"))

        with session_scope(self.session_factory) as session:
            blog, inserted = self._upsert_blog_in_session(
                session,
                url=requested_url,
                normalized_url=normalized_url,
                domain=domain,
                accepted_by="user",
            )
            if blog.crawl_status == CrawlStatus.FAILED:
                blog.crawl_status = CrawlStatus.WAITING
                blog.crawl_error_kind = None
                blog.crawl_error_message = None
            blog.updated_at = now_utc()
            self._upsert_seed_in_session(
                session,
                url=requested_url,
                normalized_url=str(blog.normalized_url),
                domain=str(blog.domain),
                blog_id=int(_business_blog_id(blog)),
                source_path="user",
                source_row=None,
            )
            blog_view = _BlogPayloadView.from_model(blog)
            return {
                "status": "QUEUED" if blog.crawl_status == CrawlStatus.WAITING else "EXISTING",
                "blog_id": int(_business_blog_id(blog)),
                "inserted": inserted,
                "blog": blog_view.as_blog_payload() if blog_view is not None else None,
            }

    def _create_user_session_payload(self, session: Session, user: UserModel) -> dict[str, Any]:
        """Create one session row and return the auth response payload.

        Args:
            session: Active SQLAlchemy session.
            user: User account that owns the new session.

        Returns:
            Auth payload containing the raw token once, its expiry, and the user
            summary.
        """

        timestamp = now_utc()
        token = token_urlsafe(32)
        session_row = UserSessionModel(
            user_id=int(user.id),
            token_hash=_hash_session_token(token),
            created_at=timestamp,
            expires_at=timestamp + timedelta(days=USER_SESSION_TTL_DAYS),
            revoked_at=None,
        )
        session.add(session_row)
        user.updated_at = timestamp
        session.flush()
        return {
            "token": token,
            "expires_at": _iso(session_row.expires_at),
            "user": _user_payload(user),
        }

    def register_user(self, *, email: str, password: str) -> dict[str, Any]:
        """Create a user account and first login session.

        Args:
            email: User email address used as the login identifier.
            password: Plaintext password to hash and store.

        Returns:
            Auth payload with bearer token and user profile.

        Raises:
            ValueError: Raised for invalid email or weak password.
            UserAuthError: Raised when the email is already registered.
        """

        normalized_email = _normalize_user_email(email)
        validated_password = _validate_password(password)
        timestamp = now_utc()
        with session_scope(self.session_factory) as session:
            existing = session.scalar(select(UserModel).where(UserModel.email == normalized_email).limit(1))
            if existing is not None:
                raise UserAuthError("email_already_registered")
            user = UserModel(
                email=normalized_email,
                password_hash=_hash_password(validated_password),
                display_name=normalized_email.split("@", 1)[0],
                created_at=timestamp,
                updated_at=timestamp,
            )
            session.add(user)
            session.flush()
            return self._create_user_session_payload(session, user)

    def login_user(self, *, email: str, password: str) -> dict[str, Any]:
        """Authenticate an existing user and create a fresh session.

        Args:
            email: User email address.
            password: Plaintext password supplied at login.

        Returns:
            Auth payload with bearer token and user profile.

        Raises:
            ValueError: Raised when the email is malformed.
            UserAuthError: Raised when credentials do not match an account.
        """

        normalized_email = _normalize_user_email(email)
        with session_scope(self.session_factory) as session:
            user = session.scalar(select(UserModel).where(UserModel.email == normalized_email).limit(1))
            if user is None or not _verify_password(password, user.password_hash):
                raise UserAuthError("invalid_credentials")
            return self._create_user_session_payload(session, user)

    def _active_user_by_session_token(self, session: Session, *, token: str) -> UserModel | None:
        """Resolve a non-expired session token to its owning user row.

        Args:
            session: Active SQLAlchemy session.
            token: Raw bearer token supplied by the caller.

        Returns:
            Matching user row, or ``None`` when the token is invalid, expired,
            revoked, or points to a missing user.
        """

        clean_token = token.strip()
        if not clean_token:
            return None
        timestamp = now_utc()
        row = session.scalar(
            select(UserSessionModel).where(
                UserSessionModel.token_hash == _hash_session_token(clean_token),
                UserSessionModel.revoked_at.is_(None),
                UserSessionModel.expires_at > timestamp,
            ).limit(1)
        )
        if row is None:
            return None
        return session.scalar(select(UserModel).where(UserModel.id == row.user_id).limit(1))

    def get_user_by_session_token(self, *, token: str) -> dict[str, Any] | None:
        """Load the current user for one bearer token.

        Args:
            token: Raw bearer session token.

        Returns:
            Public user profile payload, or ``None`` when unauthenticated.
        """

        with session_scope(self.session_factory) as session:
            user = self._active_user_by_session_token(session, token=token)
            return _user_payload(user) if user is not None else None

    def revoke_user_session(self, *, token: str) -> bool:
        """Revoke one active user session token.

        Args:
            token: Raw bearer session token.

        Returns:
            True when a session row was found and marked revoked.
        """

        clean_token = token.strip()
        if not clean_token:
            return False
        with session_scope(self.session_factory) as session:
            row = session.scalar(
                select(UserSessionModel).where(
                    UserSessionModel.token_hash == _hash_session_token(clean_token),
                    UserSessionModel.revoked_at.is_(None),
                ).limit(1)
            )
            if row is None:
                return False
            row.revoked_at = now_utc()
            session.flush()
            return True

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
            return self._serialize_ingestion_request_payload(
                session,
                request,
                serializer=_ingestion_request_payload,
            )

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
            return self._serialize_ingestion_request_payloads(
                session,
                requests,
                serializer=_priority_ingestion_request_payload,
            )

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
            identity_matches = self._lookup_blog_matches(
                session,
                query_url=query_url,
                normalized_query_url=normalized_query_url,
                statement=(
                    select(BlogModel)
                    .where(BlogModel.identity_key == identity_key)
                    .order_by(BlogModel.blog_id.asc(), BlogModel.id.asc())
                ),
                match_reason="identity_key",
            )
            if identity_matches is not None:
                return identity_matches

            normalized_matches = self._lookup_blog_matches(
                session,
                query_url=query_url,
                normalized_query_url=normalized_query_url,
                statement=(
                    select(BlogModel)
                    .where(BlogModel.normalized_url == normalized_query_url)
                    .order_by(BlogModel.blog_id.asc(), BlogModel.id.asc())
                ),
                match_reason="normalized_url",
            )
            if normalized_matches is not None:
                return normalized_matches

            return _blog_lookup_payload(
                query_url=query_url,
                normalized_query_url=normalized_query_url,
                items=[],
                match_reason=None,
            )

    def mark_ingestion_request_crawling(self, *, blog_id: int) -> None:
        with session_scope(self.session_factory) as session:
            request = self._oldest_seed_ingestion_request(
                session,
                blog_id=blog_id,
                statuses=(INGESTION_REQUEST_STATUS_QUEUED,),
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
        blog_view = _BlogPayloadView.from_model(blog)
        return blog_view.as_blog_payload() if blog_view is not None else None

    def _claim_first_matching_blog(self, session: Session, statement: Any) -> dict[str, Any] | None:
        """Claim the first blog matching a queue statement and return its payload."""
        if self.dialect_name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        return self._claim_blog_for_statement(session, statement)

    def _active_ingestion_seed_ids_statement(self) -> Any:
        """Return the active ingestion seed ids used to exclude priority-backed blogs."""
        return select(IngestionRequestModel.seed_blog_id).where(
            IngestionRequestModel.seed_blog_id.is_not(None),
            IngestionRequestModel.status.in_(tuple(ACTIVE_INGESTION_REQUEST_STATUSES)),
        )

    def _oldest_ingestion_request(
        self,
        session: Session,
        *,
        filters: tuple[ColumnElement[bool], ...],
        statuses: tuple[str, ...],
    ) -> IngestionRequestModel | None:
        """Return the oldest ingestion request matching the given filters and statuses."""
        return session.scalar(
            select(IngestionRequestModel)
            .where(
                *filters,
                IngestionRequestModel.status.in_(statuses),
            )
            .order_by(IngestionRequestModel.created_at.asc(), IngestionRequestModel.id.asc())
        )

    def _oldest_seed_ingestion_request(
        self,
        session: Session,
        *,
        blog_id: int,
        statuses: tuple[str, ...],
    ) -> IngestionRequestModel | None:
        """Return the oldest ingestion request for one seed blog within the allowed statuses."""
        return self._oldest_ingestion_request(
            session,
            filters=(IngestionRequestModel.seed_blog_id == blog_id,),
            statuses=statuses,
        )

    def _lookup_blog_matches(
        self,
        session: Session,
        *,
        query_url: str,
        normalized_query_url: str,
        statement: Any,
        match_reason: str,
    ) -> dict[str, Any] | None:
        """Return the wrapped lookup payload for one ordered blog-match query when it has matches."""
        matches = session.scalars(statement).all()
        if not matches:
            return None
        return _blog_lookup_payload(
            query_url=query_url,
            normalized_query_url=normalized_query_url,
            items=[
                blog_view.as_blog_payload()
                for item in matches
                if (blog_view := _BlogPayloadView.from_model(item)) is not None
            ],
            match_reason=match_reason,
        )

    def _priority_blog_claim_statement(self) -> Any:
        """Build the priority queue statement without changing claim semantics."""
        return (
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

    def _waiting_blog_claim_statement(self, *, include_priority: bool) -> Any:
        """Build the waiting queue statement while preserving priority exclusion semantics."""
        statement = select(BlogModel).where(BlogModel.crawl_status == CrawlStatus.WAITING)
        if not include_priority:
            statement = statement.where(
                BlogModel.blog_id.not_in(self._active_ingestion_seed_ids_statement())
            )
        return statement.order_by(BlogModel.blog_id.asc(), BlogModel.id.asc()).limit(1)

    def get_next_priority_blog(self) -> dict[str, Any] | None:
        with session_scope(self.session_factory) as session:
            return self._claim_first_matching_blog(session, self._priority_blog_claim_statement())

    def get_next_waiting_blog(self, *, include_priority: bool = True) -> dict[str, Any] | None:
        with session_scope(self.session_factory) as session:
            return self._claim_first_matching_blog(
                session,
                self._waiting_blog_claim_statement(include_priority=include_priority),
            )

    def requeue_failed_blogs(self) -> dict[str, Any]:
        """Move every failed blog back into the waiting crawl queue.

        Returns:
            Payload containing the number of blog rows changed from `FAILED` to
            `WAITING`.
        """
        with session_scope(self.session_factory) as session:
            blogs = session.scalars(select(BlogModel).where(BlogModel.crawl_status == CrawlStatus.FAILED)).all()
            requeued_count = len(blogs)
            timestamp = now_utc()
            for blog in blogs:
                blog.crawl_status = CrawlStatus.WAITING
                blog.status_code = None
                blog.crawl_error_kind = None
                blog.crawl_error_message = None
                blog.updated_at = timestamp

            requests = session.scalars(
                select(IngestionRequestModel).where(
                    IngestionRequestModel.seed_blog_id.in_([int(_business_blog_id(blog)) for blog in blogs]),
                    IngestionRequestModel.status == INGESTION_REQUEST_STATUS_FAILED,
                )
            ).all()
            for request in requests:
                request.status = INGESTION_REQUEST_STATUS_QUEUED
                request.error_message = None
                request.updated_at = timestamp

            return {"requeued": requeued_count}

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
        with session_scope(self.session_factory) as session:
            blog = self._get_blog_by_business_id(session, blog_id)
            if blog is None:
                return
            resolved_status = CrawlStatus(crawl_status)
            timestamp = now_utc()
            blog.crawl_status = resolved_status
            blog.status_code = status_code
            blog.friend_links_count = friend_links_count
            blog.last_crawled_at = timestamp
            blog.last_crawl_attempt_at = timestamp
            blog.updated_at = timestamp
            if resolved_status == CrawlStatus.FINISHED:
                blog.successful_crawl_at = timestamp
                blog.crawl_error_kind = None
                blog.crawl_error_message = None
            elif resolved_status == CrawlStatus.FAILED:
                blog.crawl_error_kind = crawl_error_kind
                blog.crawl_error_message = crawl_error_message
            if metadata_captured:
                blog.title = title
                blog.icon_url = icon_url
            request = self._oldest_seed_ingestion_request(
                session,
                blog_id=blog_id,
                statuses=tuple(ACTIVE_INGESTION_REQUEST_STATUSES),
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
        """Create one raw discovered URL and return its row ID.

        Args:
            source_blog_id: Business blog ID of the source page.
            normalized_url: Normalized candidate URL discovered by the crawler.
            status: Initial status requested by the caller.

        Returns:
            Database row ID of the inserted raw URL. Duplicate URLs are stored
            with duplicate status before the normal filter chain is applied.
        """

        return int(
            self.create_raw_discovered_url_record(
                source_blog_id=source_blog_id,
                normalized_url=normalized_url,
                status=status,
            )["id"]
        )

    def create_raw_discovered_url_record(
        self,
        *,
        source_blog_id: int,
        normalized_url: str,
        status: str,
    ) -> dict[str, Any]:
        """Create one raw discovered URL and return its persisted status.

        Args:
            source_blog_id: Business blog ID of the source page.
            normalized_url: Normalized candidate URL discovered by the crawler.
            status: Initial status requested by the caller.

        Returns:
            Payload with ``id`` and ``status``. When an older row with the
            same normalized URL already exists, the stored status is
            ``rule:duplicate_url`` so duplicate URLs are filtered before the
            normal configurable chain. Newer rows are ignored by this check.
        """

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
            previous_id = session.scalar(
                select(RawDiscoveredUrlModel.id)
                .where(
                    RawDiscoveredUrlModel.id < int(record.id),
                    RawDiscoveredUrlModel.normalized_url == normalized_url,
                )
                .order_by(RawDiscoveredUrlModel.id.asc())
                .limit(1)
            )
            stored_status = RAW_DISCOVERED_URL_DUPLICATE_STATUS if previous_id is not None else status
            record.status = stored_status
            record.updated_at = now_utc()
            session.flush()
            return {"id": int(record.id), "status": str(record.status)}

    def find_blog_id_by_normalized_url(self, *, normalized_url: str) -> int | None:
        """Return the persisted blog id for one normalized URL when it exists.

        Args:
            normalized_url: Canonical URL value used by crawler discovery and
                blog upsert identity checks.

        Returns:
            Business ``blog_id`` for the matching blog, or ``None`` when the
            URL has not yet been accepted as a blog.
        """

        identity = resolve_blog_identity(normalized_url)
        with session_scope(self.session_factory) as session:
            blog_id = session.scalar(
                select(BlogModel.blog_id)
                .where(BlogModel.normalized_url == normalized_url)
                .order_by(BlogModel.blog_id.asc(), BlogModel.id.asc())
                .limit(1)
            )
            if blog_id is not None:
                return int(blog_id)
            blog_id = session.scalar(
                select(BlogModel.blog_id)
                .where(BlogModel.identity_key == identity.identity_key)
                .order_by(BlogModel.blog_id.asc(), BlogModel.id.asc())
                .limit(1)
            )
            return int(blog_id) if blog_id is not None else None

    def update_raw_discovered_url_status(
        self,
        *,
        record_id: int,
        status: str,
        accepted_by: str | None = None,
    ) -> None:
        with session_scope(self.session_factory) as session:
            record = self._require_model(
                session,
                RawDiscoveredUrlModel,
                record_id,
                not_found_error="raw_discovered_url_not_found",
            )
            record.status = status
            record.accepted_by = accepted_by if status == RAW_DISCOVERED_URL_SUCCESS_STATUS else None
            record.updated_at = now_utc()

    def _labelable_raw_url_condition(self) -> ColumnElement[bool]:
        """Return the shared SQL predicate for labelable raw URL statuses.

        Args:
            None.

        Returns:
            SQLAlchemy predicate matching ``success`` and ``model:*`` raw URL
            rows.
        """

        return or_(
            RawDiscoveredUrlModel.status == "success",
            RawDiscoveredUrlModel.status.like(f"{BLOG_LABELING_MODEL_FILTER_STATUS_PREFIX}%"),
        )

    def _labelable_raw_url_targets(self, session: Session) -> list[dict[str, Any]]:
        """Load distinct labelable raw URLs with resolved label target IDs.

        Args:
            session: Active SQLAlchemy session.

        Returns:
            Ordered dictionaries containing ``target_id``, ``raw_id``, and
            ``normalized_url``. ``target_id`` is always the earliest raw row ID
            for that URL.
        """

        raw_urls = (
            select(
                func.min(RawDiscoveredUrlModel.id).label("raw_id"),
                RawDiscoveredUrlModel.normalized_url.label("normalized_url"),
                func.min(RawDiscoveredUrlModel.discovered_at).label("raw_created_at"),
                func.max(RawDiscoveredUrlModel.updated_at).label("raw_updated_at"),
            )
            .where(self._labelable_raw_url_condition())
            .group_by(RawDiscoveredUrlModel.normalized_url)
            .subquery()
        )
        rows = session.execute(
            select(
                raw_urls.c.raw_id.label("target_id"),
                raw_urls.c.raw_id,
                raw_urls.c.normalized_url,
                raw_urls.c.raw_created_at,
                raw_urls.c.raw_updated_at,
            )
            .outerjoin(BlogModel, BlogModel.normalized_url == raw_urls.c.normalized_url)
            .order_by(raw_urls.c.raw_id.asc())
        ).all()
        return [
            {
                "target_id": int(row.target_id),
                "raw_id": int(row.raw_id),
                "normalized_url": str(row.normalized_url),
                "raw_created_at": row.raw_created_at,
                "raw_updated_at": row.raw_updated_at,
            }
            for row in rows
        ]

    def _labelable_target_id_for_url_in_session(self, session: Session, *, url: str) -> int | None:
        """Resolve the label target ID for one eligible raw URL.

        Args:
            session: Active SQLAlchemy session.
            url: Raw or normalized URL.

        Returns:
            Earliest matching ``raw_discovered_urls.id``. ``None`` means the
            URL is outside the labelable raw URL pool.
        """

        normalized = normalize_url(url)
        identity = resolve_blog_identity(url)
        candidates = [url, normalized.normalized_url]
        if identity.is_homepage:
            candidates.append(identity.canonical_url)
        raw = session.execute(
            select(RawDiscoveredUrlModel)
            .where(
                self._labelable_raw_url_condition(),
                RawDiscoveredUrlModel.normalized_url.in_(candidates),
            )
            .order_by(RawDiscoveredUrlModel.id.asc())
            .limit(1)
        ).scalar_one_or_none()
        if raw is None:
            return None
        return int(raw.id)

    def ensure_labelable_raw_url_blogs(self) -> dict[str, int]:
        """Return current labelable raw URL coverage without creating blogs.

        Args:
            None.

        Returns:
            Counts describing inspected raw URLs. ``created`` is always zero
            because the labeling flow no longer creates lightweight blogs.
        """

        with session_scope(self.session_factory) as session:
            return {"inspected": len(self._labelable_raw_url_targets(session)), "created": 0}

    def get_labelable_blog_by_url(self, *, url: str) -> dict[str, Any] | None:
        """Return the current label target for one eligible raw URL.

        Args:
            url: URL from a legacy label CSV or labeling workflow.

        Returns:
            Label target payload when the URL is in the shared labelable raw
            URL pool; otherwise ``None``. The payload may be backed by an
            existing blog row or by the raw URL row itself.
        """

        normalized = normalize_url(url)
        identity = resolve_blog_identity(url)
        normalized_query_url = identity.canonical_url if identity.is_homepage else normalized.normalized_url
        with session_scope(self.session_factory) as session:
            raw = session.scalar(
                select(RawDiscoveredUrlModel)
                .where(
                    self._labelable_raw_url_condition(),
                    RawDiscoveredUrlModel.normalized_url.in_([url, normalized.normalized_url, normalized_query_url]),
                )
                .order_by(RawDiscoveredUrlModel.id.asc())
                .limit(1)
            )
            if raw is None:
                return None
            row = session.execute(
                self._blog_select()[0].where(
                    or_(
                        BlogModel.normalized_url == raw.normalized_url,
                        BlogModel.url == url,
                        BlogModel.identity_key == identity.identity_key,
                    )
                )
            ).first()
            if row is not None:
                return self._row_blog_payload(row)
            raw_normalized = normalize_url(raw.normalized_url)
            return {
                "id": int(raw.id),
                "blog_id": int(raw.id),
                "url": raw.normalized_url,
                "normalized_url": raw.normalized_url,
                "domain": raw_normalized.domain,
                "title": "",
                "icon_url": None,
                "crawl_status": None,
            }

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
        acceptance_status: str | None = BLOG_ACCEPTANCE_ACCEPTED,
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
            acceptance_status=acceptance_status,
        )
        with session_scope(self.session_factory) as session:
            statement, metrics = self._blog_select()
            if query["acceptance_status"] is not None:
                statement = statement.where(BlogModel.acceptance_status == query["acceptance_status"])
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
                    and_(BlogModel.icon_url.is_not(None), BlogModel.icon_url != "")
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
                statement = self._random_blog_catalog_statement(statement)
            else:
                statement = statement.order_by(BlogModel.blog_id.desc(), BlogModel.id.desc())

            rows, total_items, effective_page = _execute_paginated_query(
                session,
                statement,
                page=query["page"],
                page_size=query["page_size"],
            )
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
                    "acceptance_status": query["acceptance_status"],
                },
            )

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
        """Persist one random-blog recommendation request and its impressions.

        Args:
            count: Number of cards requested by the frontend.
            visitor_id: Stable anonymous visitor identifier.
            session_id: Stable browser-session identifier.
            user_id: Optional authenticated user ID for attribution.
            source: Optional caller surface detail.
            page_url: Optional page URL where the batch was shown.
            context: Optional JSON metadata associated with the serving event.

        Returns:
            Recommendation batch payload containing request metadata and ordered
            catalog items with impression attribution fields.
        """

        if count < 1 or count > 50:
            raise ValueError("count_out_of_range")
        clean_visitor_id = _clean_event_text(visitor_id, field="visitor_id")
        clean_session_id = _clean_event_text(session_id, field="session_id")
        request_uuid = token_urlsafe(24)
        with session_scope(self.session_factory) as session:
            if user_id is not None and session.scalar(select(UserModel.id).where(UserModel.id == user_id)) is None:
                raise UserAuthError("user_not_found")
            statement, _ = self._blog_select()
            statement = statement.where(
                BlogModel.crawl_status == CrawlStatus.FINISHED,
                BlogModel.acceptance_status == BLOG_ACCEPTANCE_ACCEPTED,
            )
            rows = session.execute(self._random_blog_catalog_statement(statement).limit(count)).all()
            recommendation = RecommendationRequestModel(
                request_uuid=request_uuid,
                surface=RANDOM_RECOMMENDATION_SURFACE,
                strategy=RANDOM_RECOMMENDATION_STRATEGY,
                strategy_version=RANDOM_RECOMMENDATION_STRATEGY_VERSION,
                visitor_id=clean_visitor_id,
                user_id=user_id,
                session_id=clean_session_id,
                source=(source or "").strip() or None,
                page_url=(page_url or "").strip() or None,
                requested_count=count,
                served_count=len(rows),
                context_json=_coerce_json_object(context),
            )
            session.add(recommendation)
            session.flush()
            items: list[dict[str, Any]] = []
            for position, row in enumerate(rows, start=1):
                blog = row[0]
                blog_id = _business_blog_id(blog)
                impression = RecommendationImpressionModel(
                    request_id=recommendation.id,
                    blog_id=int(blog_id),
                    normalized_url=str(blog.normalized_url),
                    position=position,
                    score=None,
                    reason_json={"strategy": RANDOM_RECOMMENDATION_STRATEGY},
                )
                session.add(impression)
                session.flush()
                items.append(
                    self._row_blog_payload(row)
                    | {
                        "request_uuid": request_uuid,
                        "impression_id": impression.id,
                        "position": position,
                    }
                )
            session.flush()
            return {
                "request_uuid": request_uuid,
                "surface": RANDOM_RECOMMENDATION_SURFACE,
                "strategy": RANDOM_RECOMMENDATION_STRATEGY,
                "strategy_version": RANDOM_RECOMMENDATION_STRATEGY_VERSION,
                "visitor_id": clean_visitor_id,
                "session_id": clean_session_id,
                "user_id": user_id,
                "source": recommendation.source,
                "page_url": recommendation.page_url,
                "requested_count": count,
                "served_count": len(items),
                "created_at": _iso(recommendation.created_at),
                "items": items,
            }

    def _blog_interaction_payload(self, interaction: BlogInteractionModel) -> dict[str, Any]:
        """Serialize one immutable blog interaction event row.

        Args:
            interaction: Persisted interaction model.

        Returns:
            JSON-ready event payload with attribution identifiers.
        """

        return {
            "id": interaction.id,
            "event_uuid": interaction.event_uuid,
            "request_id": interaction.request_id,
            "impression_id": interaction.impression_id,
            "blog_id": interaction.blog_id,
            "normalized_url": interaction.normalized_url,
            "event_type": interaction.event_type,
            "position": interaction.position,
            "entrance_kind": interaction.entrance_kind,
            "entrance_url": interaction.entrance_url,
            "interaction_order": interaction.interaction_order,
            "visitor_id": interaction.visitor_id,
            "user_id": interaction.user_id,
            "session_id": interaction.session_id,
            "client_event_at": _iso(interaction.client_event_at),
            "attributes": interaction.attributes_json,
            "created_at": _iso(interaction.created_at),
        }

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
        client_event_at: str | datetime | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist one idempotent recommendation interaction event.

        Args:
            event_uuid: Client-generated idempotency key.
            event_type: Interaction type such as ``detail_open``.
            blog_id: Public/business blog ID receiving the event.
            visitor_id: Stable anonymous visitor identifier.
            session_id: Stable browser-session identifier.
            entrance_kind: Stable entrance category such as ``random_blog_card``.
            entrance_url: Raw URL for the entrance context.
            request_uuid: Optional serving request UUID for attribution.
            impression_id: Optional impression row ID for attribution.
            position: Optional card position displayed to the visitor.
            interaction_order: Monotonic client-side order within the session.
            user_id: Optional authenticated user ID.
            client_event_at: Optional client timestamp.
            attributes: Optional JSON metadata for the event.

        Returns:
            Serialized event payload plus a ``duplicate`` flag.
        """

        clean_event_uuid = _clean_event_text(event_uuid, field="event_uuid")
        clean_event_type = _clean_event_text(event_type, field="event_type", max_length=64)
        if clean_event_type not in RECOMMENDATION_EVENT_TYPES:
            raise ValueError("unsupported_recommendation_event_type")
        clean_visitor_id = _clean_event_text(visitor_id, field="visitor_id")
        clean_session_id = _clean_event_text(session_id, field="session_id")
        clean_entrance_kind = _clean_event_text(entrance_kind, field="entrance_kind", max_length=128)
        clean_entrance_url = _clean_event_text(entrance_url, field="entrance_url", max_length=2048)
        if interaction_order < 1:
            raise ValueError("interaction_order_out_of_range")
        with session_scope(self.session_factory) as session:
            existing = session.scalar(
                select(BlogInteractionModel).where(BlogInteractionModel.event_uuid == clean_event_uuid)
            )
            if existing is not None:
                return self._blog_interaction_payload(existing) | {"duplicate": True}
            blog = self._get_blog_by_business_id(session, blog_id)
            if blog is None:
                raise BlogLabelingNotFoundError("blog_not_found")
            if user_id is not None and session.scalar(select(UserModel.id).where(UserModel.id == user_id)) is None:
                raise UserAuthError("user_not_found")
            recommendation: RecommendationRequestModel | None = None
            if request_uuid is not None:
                recommendation = session.scalar(
                    select(RecommendationRequestModel).where(
                        RecommendationRequestModel.request_uuid == request_uuid
                    )
                )
                if recommendation is None:
                    raise ValueError("recommendation_request_not_found")
            impression: RecommendationImpressionModel | None = None
            if impression_id is not None:
                impression = session.get(RecommendationImpressionModel, impression_id)
                if impression is None:
                    raise ValueError("recommendation_impression_not_found")
                if int(impression.blog_id) != int(blog_id):
                    raise ValueError("recommendation_impression_blog_mismatch")
                if recommendation is not None and int(impression.request_id) != int(recommendation.id):
                    raise ValueError("recommendation_impression_request_mismatch")
                if position is None:
                    position = int(impression.position)
            interaction = BlogInteractionModel(
                event_uuid=clean_event_uuid,
                request_id=recommendation.id if recommendation is not None else None,
                impression_id=impression.id if impression is not None else None,
                blog_id=int(blog_id),
                normalized_url=str(blog.normalized_url),
                event_type=clean_event_type,
                position=position,
                entrance_kind=clean_entrance_kind,
                entrance_url=clean_entrance_url,
                interaction_order=interaction_order,
                visitor_id=clean_visitor_id,
                user_id=user_id,
                session_id=clean_session_id,
                client_event_at=_parse_event_datetime(client_event_at),
                attributes_json=_coerce_json_object(attributes),
            )
            session.add(interaction)
            session.flush()
            return self._blog_interaction_payload(interaction) | {"duplicate": False}

    def get_blog_recommendation_stats(self, blog_id: int) -> dict[str, Any] | None:
        """Return recommendation exposure and interaction stats for one blog.

        Args:
            blog_id: Public/business blog ID.

        Returns:
            Stats payload, or ``None`` when the blog does not exist.
        """

        with session_scope(self.session_factory) as session:
            blog = self._get_blog_by_business_id(session, blog_id)
            if blog is None:
                return None
            impressions = int(
                session.scalar(
                    select(func.count(RecommendationImpressionModel.id)).where(
                        RecommendationImpressionModel.blog_id == blog_id
                    )
                )
                or 0
            )
            event_counts = {
                str(event_type): int(count or 0)
                for event_type, count in session.execute(
                    select(BlogInteractionModel.event_type, func.count(BlogInteractionModel.id))
                    .where(BlogInteractionModel.blog_id == blog_id)
                    .group_by(BlogInteractionModel.event_type)
                ).all()
            }
            unique_visitors = int(
                session.scalar(
                    select(func.count(func.distinct(BlogInteractionModel.visitor_id))).where(
                        BlogInteractionModel.blog_id == blog_id
                    )
                )
                or 0
            )
            last_interaction_at = session.scalar(
                select(func.max(BlogInteractionModel.created_at)).where(BlogInteractionModel.blog_id == blog_id)
            )
            clicks = int(event_counts.get("click", 0))
            detail_opens = int(event_counts.get("detail_open", 0))
            external_opens = int(event_counts.get("external_open", 0))
            label_selects = int(event_counts.get("label_select", 0))
            return {
                "blog_id": blog_id,
                "normalized_url": blog.normalized_url,
                "impressions": impressions,
                "clicks": clicks,
                "detail_opens": detail_opens,
                "external_opens": external_opens,
                "label_selects": label_selects,
                "unique_visitors": unique_visitors,
                "ctr": (clicks + detail_opens + external_opens) / impressions if impressions else 0.0,
                "last_interaction_at": _iso(last_interaction_at),
                "by_event_type": event_counts,
            }

    def get_recommendation_strategy_stats(self) -> dict[str, Any]:
        """Return aggregate recommendation request, impression, and event stats.

        Args:
            None.

        Returns:
            Strategy-grouped aggregate stats for admin dashboards.
        """

        with session_scope(self.session_factory) as session:
            total_requests = int(session.scalar(select(func.count(RecommendationRequestModel.id))) or 0)
            total_impressions = int(session.scalar(select(func.count(RecommendationImpressionModel.id))) or 0)
            total_interactions = int(session.scalar(select(func.count(BlogInteractionModel.id))) or 0)
            click_counts = {
                int(request_id): int(count or 0)
                for request_id, count in session.execute(
                    select(BlogInteractionModel.request_id, func.count(BlogInteractionModel.id))
                    .where(
                        BlogInteractionModel.request_id.is_not(None),
                        BlogInteractionModel.event_type.in_(("click", "detail_open", "external_open")),
                    )
                    .group_by(BlogInteractionModel.request_id)
                ).all()
            }
            grouped_rows = session.execute(
                select(
                    RecommendationRequestModel.surface,
                    RecommendationRequestModel.strategy,
                    RecommendationRequestModel.strategy_version,
                    func.count(RecommendationRequestModel.id),
                    func.coalesce(func.sum(RecommendationRequestModel.served_count), 0),
                    func.count(func.distinct(RecommendationRequestModel.visitor_id)),
                ).group_by(
                    RecommendationRequestModel.surface,
                    RecommendationRequestModel.strategy,
                    RecommendationRequestModel.strategy_version,
                )
            ).all()
            by_strategy: list[dict[str, Any]] = []
            for surface, strategy, strategy_version, request_count, served_count, visitor_count in grouped_rows:
                request_ids = session.scalars(
                    select(RecommendationRequestModel.id).where(
                        RecommendationRequestModel.surface == surface,
                        RecommendationRequestModel.strategy == strategy,
                        RecommendationRequestModel.strategy_version == strategy_version,
                    )
                ).all()
                clicks = sum(click_counts.get(int(request_id), 0) for request_id in request_ids)
                impressions = int(served_count or 0)
                by_strategy.append(
                    {
                        "surface": surface,
                        "strategy": strategy,
                        "strategy_version": strategy_version,
                        "requests": int(request_count or 0),
                        "impressions": impressions,
                        "clicks": clicks,
                        "unique_visitors": int(visitor_count or 0),
                        "ctr": clicks / impressions if impressions else 0.0,
                    }
                )
            return {
                "total_requests": total_requests,
                "total_impressions": total_impressions,
                "total_interactions": total_interactions,
                "by_strategy": by_strategy,
            }

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
            earlier_raw = aliased(RawDiscoveredUrlModel)
            representative_raw = (
                ~select(earlier_raw.id)
                .where(
                    earlier_raw.normalized_url == RawDiscoveredUrlModel.normalized_url,
                    earlier_raw.id < RawDiscoveredUrlModel.id,
                    or_(
                        earlier_raw.status == "success",
                        earlier_raw.status.like(f"{BLOG_LABELING_MODEL_FILTER_STATUS_PREFIX}%"),
                    ),
                )
                .exists()
            )
            latest_labeled_at = (
                select(
                    BlogLabelModel.normalized_url.label("normalized_url"),
                    BlogLabelModel.title.label("label_title"),
                    BlogLabelModel.updated_time.label("last_labeled_at"),
                )
                .subquery()
            )
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
            target_id = RawDiscoveredUrlModel.id.label("target_id")
            activity_at = func.coalesce(
                BlogModel.last_crawled_at,
                BlogModel.updated_at,
                RawDiscoveredUrlModel.updated_at,
            ).label("activity_at")
            statement = (
                select(
                    target_id,
                    RawDiscoveredUrlModel.id.label("raw_id"),
                    RawDiscoveredUrlModel.normalized_url,
                    RawDiscoveredUrlModel.discovered_at.label("raw_created_at"),
                    RawDiscoveredUrlModel.updated_at.label("raw_updated_at"),
                    BlogModel.url.label("blog_url"),
                    BlogModel.domain.label("blog_domain"),
                    BlogModel.identity_key,
                    BlogModel.identity_reason_codes,
                    BlogModel.identity_ruleset_version,
                    BlogModel.email,
                    BlogModel.title,
                    BlogModel.icon_url,
                    BlogModel.status_code,
                    BlogModel.crawl_status,
                    BlogModel.friend_links_count,
                    BlogModel.last_crawled_at,
                    BlogModel.created_at.label("blog_created_at"),
                    BlogModel.updated_at.label("blog_updated_at"),
                    func.coalesce(incoming_counts.c.incoming_count, 0).label("incoming_count"),
                    func.coalesce(outgoing_counts.c.outgoing_count, 0).label("outgoing_count"),
                    activity_at,
                    latest_labeled_at.c.last_labeled_at.label("last_labeled_at"),
                    latest_labeled_at.c.label_title.label("label_title"),
                )
                .select_from(RawDiscoveredUrlModel)
                .outerjoin(BlogModel, BlogModel.normalized_url == RawDiscoveredUrlModel.normalized_url)
                .outerjoin(incoming_counts, incoming_counts.c.blog_id == BlogModel.blog_id)
                .outerjoin(outgoing_counts, outgoing_counts.c.blog_id == BlogModel.blog_id)
                .outerjoin(latest_labeled_at, latest_labeled_at.c.normalized_url == RawDiscoveredUrlModel.normalized_url)
                .where(self._labelable_raw_url_condition(), representative_raw)
            )
            if query["q"] is not None:
                pattern = f"%{query['q']}%"
                statement = statement.where(
                    or_(
                        BlogModel.title.ilike(pattern),
                        latest_labeled_at.c.label_title.ilike(pattern),
                        BlogModel.domain.ilike(pattern),
                        BlogModel.url.ilike(pattern),
                        RawDiscoveredUrlModel.normalized_url.ilike(pattern),
                    )
                )
            if query["label"] is not None:
                try:
                    label_filter = str(_label_id_from_name_in_session(session, str(query["label"])))
                except ValueError:
                    label_filter = str(query["label"])
                statement = statement.where(
                    RawDiscoveredUrlModel.normalized_url.in_(
                        select(BlogLabelModel.normalized_url)
                        .where(BlogLabelModel.label_id[label_filter].is_not(None))
                    )
                )
            if query["labeled"] is True:
                statement = statement.where(latest_labeled_at.c.last_labeled_at.is_not(None))
            elif query["labeled"] is False:
                statement = statement.where(latest_labeled_at.c.last_labeled_at.is_(None))

            if query["sort"] == "recent_activity":
                statement = statement.order_by(
                    activity_at.desc(),
                    target_id.desc(),
                )
            elif query["sort"] == "recently_labeled":
                statement = statement.order_by(
                    latest_labeled_at.c.last_labeled_at.desc().nullslast(),
                    target_id.desc(),
                )
            else:
                statement = statement.order_by(target_id.desc())

            rows, total_items, effective_page = _execute_paginated_query(
                session,
                statement,
                page=query["page"],
                page_size=query["page_size"],
            )
            label_names_by_id = _blog_label_names_by_id(session)
            normalized_urls = [str(row.normalized_url) for row in rows]
            target_id_by_url = {str(row.normalized_url): int(row.target_id) for row in rows}
            label_rows_by_url = self._blog_label_rows_by_url(
                session,
                normalized_urls=normalized_urls,
            )
            label_states_by_url = {
                normalized_url: _BlogLabelStateView.from_assignment_rows(
                    blog_id=target_id_by_url[normalized_url],
                    label_counts=_normalize_label_counts(label_rows_by_url[normalized_url].label_id),
                    last_labeled_at=label_rows_by_url[normalized_url].updated_time,
                    label_names=label_names_by_id,
                )
                for normalized_url in normalized_urls
                if normalized_url in label_rows_by_url
            }
            display_titles_by_url: dict[str, str] = {}
            for row in rows:
                normalized_url = str(row.normalized_url)
                label_title = str(row.label_title or "").strip()
                blog_title = str(row.title or "").strip()
                display_title = label_title or blog_title
                display_titles_by_url[normalized_url] = display_title
                label_row = label_rows_by_url.get(normalized_url)
                if label_row is not None and not label_title and blog_title:
                    label_row.title = blog_title
            available_tags = _blog_label_tag_payloads(session)
            return _catalog_response(
                items=[
                    _raw_blog_labeling_payload(
                        row,
                        label_state=label_states_by_url.get(
                            str(row.normalized_url),
                            _BlogLabelStateView.empty(
                                blog_id=int(row.target_id),
                                last_labeled_at=row.last_labeled_at,
                                label_names=label_names_by_id,
                            ),
                        ),
                        display_title=display_titles_by_url.get(str(row.normalized_url), ""),
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
            return _blog_label_tag_payloads(session)

    def get_blog_label_counts(self) -> dict[str, Any]:
        """Return persisted label URL counts grouped by label slug.

        Returns:
            Summary backed by every row in ``blog_labels``; ``total_labeled``
            counts URLs with at least one label, while ``by_label`` counts URLs
            containing each label id.
        """

        with session_scope(self.session_factory) as session:
            label_names_by_id = _blog_label_names_by_id(session)
            counts_by_label: dict[str, int] = {slug: 0 for slug in label_names_by_id.values()}
            total_labeled = 0
            rows = session.scalars(select(BlogLabelModel.label_id)).all()
            for raw_counts in rows:
                label_counts = _normalize_label_counts(raw_counts)
                if not label_counts:
                    continue
                total_labeled += 1
                for label_id in label_counts:
                    label_slug = label_names_by_id.get(int(label_id), str(label_id))
                    counts_by_label[label_slug] = int(counts_by_label.get(label_slug, 0)) + 1
            return {
                "total_labeled": total_labeled,
                "by_label": counts_by_label,
            }

    def _blog_label_training_rows(self, session: Session) -> list[Any]:
        """Load the canonical labeled training rows in deterministic order.

        Args:
            session: Active SQLAlchemy session.

        Returns:
            Ordered rows containing ``url``, ``title``, and ``label_name``.
        """

        label_names_by_id = _blog_label_names_by_id(session)
        label_rows = session.execute(
            select(
                BlogLabelModel.normalized_url,
                BlogLabelModel.title.label("title"),
                BlogLabelModel.label_id.label("label_counts"),
            )
            .order_by(BlogLabelModel.normalized_url.asc())
        ).all()
        expanded_rows: list[dict[str, str]] = []
        for row in label_rows:
            for label_id in sorted(_normalize_label_counts(row.label_counts), key=int):
                expanded_rows.append(
                    {
                        "url": str(row.normalized_url),
                        "title": row.title or "",
                        "label_name": label_names_by_id.get(int(label_id), label_id),
                    }
                )
        return expanded_rows

    def _blog_label_training_records(self, session: Session) -> list[dict[str, str]]:
        """Load canonical labeled training records for export snapshots.

        Args:
            session: Active SQLAlchemy session.

        Returns:
            Ordered dictionaries with only ``url``, ``title``, and ``label``.
        """

        return [
            {
                "url": str(row["url"] if isinstance(row, dict) else row.url),
                "title": (row["title"] if isinstance(row, dict) else row.title) or "",
                "label": str(row["label_name"] if isinstance(row, dict) else row.label_name),
            }
            for row in self._blog_label_training_rows(session)
        ]

    def _write_blog_label_training_parquet(
        self,
        records: list[dict[str, str]],
        *,
        parquet_path: Path,
    ) -> None:
        """Atomically write labeled training records to the parquet snapshot.

        Args:
            records: Canonical label records to serialize.
            parquet_path: Destination parquet file path.

        Returns:
            None. The file is replaced atomically after a successful write.
        """

        pa = _require_pyarrow()
        pq = _require_pyarrow_parquet()
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pylist(
            records,
            schema=pa.schema(
                [
                    ("url", pa.string()),
                    ("title", pa.string()),
                    ("label", pa.string()),
                ]
            ),
        )
        with tempfile.NamedTemporaryFile(
            dir=parquet_path.parent,
            prefix=f".{parquet_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
        try:
            pq.write_table(table, temporary_path)
            temporary_path.replace(parquet_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def _read_blog_label_training_parquet_records(self, parquet_path: Path) -> list[dict[str, str]]:
        """Read the current parquet snapshot into normalized label records.

        Args:
            parquet_path: Existing parquet file path.

        Returns:
            Records containing ``url``, ``title``, and ``label``.
        """

        if not parquet_path.exists():
            return []
        pq = _require_pyarrow_parquet()
        table = pq.read_table(parquet_path, columns=["url", "title", "label"])
        return [
            {
                "url": str(row.get("url") or ""),
                "title": str(row.get("title") or ""),
                "label": str(row.get("label") or ""),
            }
            for row in table.to_pylist()
        ]

    def _blog_label_training_status_payload(
        self,
        *,
        parquet_path: Path,
        total_labeled: int,
        saved_count: int,
        missing_count: int,
        rewritten: bool,
        message: str,
    ) -> dict[str, Any]:
        """Build the shared parquet status/action response payload.

        Args:
            parquet_path: Canonical parquet snapshot path.
            total_labeled: Current count of labeled ``blog x label`` rows.
            saved_count: Current count of rows persisted in parquet.
            missing_count: Number of labeled rows not present in parquet.
            rewritten: Whether this action wrote a new parquet snapshot.
            message: Operator-facing progress/result message.

        Returns:
            JSON-serializable parquet export status payload.
        """

        return {
            "path": str(parquet_path),
            "filename": parquet_path.name,
            "exists": parquet_path.exists(),
            "saved_count": saved_count,
            "total_labeled": total_labeled,
            "missing_count": missing_count,
            "batch_size": BLOG_LABELING_PARQUET_BATCH_SIZE,
            "rewritten": rewritten,
            "message": message,
            "updated_at": _iso(now_utc()),
        }

    def get_blog_label_training_parquet_status(self) -> dict[str, Any]:
        parquet_path = _blog_label_training_parquet_path(self.decision_settings)
        with session_scope(self.session_factory) as session:
            records = self._blog_label_training_records(session)
        saved_records = self._read_blog_label_training_parquet_records(parquet_path)
        missing_count = len({(record["url"], record["label"]) for record in records} - {(record["url"], record["label"]) for record in saved_records})
        return self._blog_label_training_status_payload(
            parquet_path=parquet_path,
            total_labeled=len(records),
            saved_count=len(saved_records),
            missing_count=missing_count,
            rewritten=False,
            message=f"已保存 {len(saved_records)} 条数据，总计有 label 的有 {len(records)} 条数据。",
        )

    def sync_blog_label_training_parquet(self) -> dict[str, Any]:
        parquet_path = _blog_label_training_parquet_path(self.decision_settings)
        with session_scope(self.session_factory) as session:
            records = self._blog_label_training_records(session)
        saved_records = self._read_blog_label_training_parquet_records(parquet_path)
        record_keys = {(record["url"], record["label"]) for record in records}
        saved_keys = {(record["url"], record["label"]) for record in saved_records}
        missing_count = len(record_keys - saved_keys)
        should_rewrite = (
            not parquet_path.exists()
            or missing_count > 0
            or len(records) < len(saved_records)
            or (len(records) > 0 and len(records) % BLOG_LABELING_PARQUET_BATCH_SIZE == 0)
        )
        if should_rewrite:
            self._write_blog_label_training_parquet(records, parquet_path=parquet_path)
            return self._blog_label_training_status_payload(
                parquet_path=parquet_path,
                total_labeled=len(records),
                saved_count=len(records),
                missing_count=0,
                rewritten=True,
                message=f"已保存 {len(records)} 条数据，总计有 label 的有 {len(records)} 条数据。",
            )
        return self._blog_label_training_status_payload(
            parquet_path=parquet_path,
            total_labeled=len(records),
            saved_count=len(saved_records),
            missing_count=missing_count,
            rewritten=False,
            message=f"无需重新保存：已保存 {len(saved_records)} 条数据，总计有 label 的有 {len(records)} 条数据。",
        )

    def rebuild_blog_label_training_parquet(self) -> dict[str, Any]:
        parquet_path = _blog_label_training_parquet_path(self.decision_settings)
        with session_scope(self.session_factory) as session:
            records = self._blog_label_training_records(session)
        self._write_blog_label_training_parquet(records, parquet_path=parquet_path)
        return self._blog_label_training_status_payload(
            parquet_path=parquet_path,
            total_labeled=len(records),
            saved_count=len(records),
            missing_count=0,
            rewritten=True,
            message=f"已重置 parquet 文件并重新保存 {len(records)} 条数据。",
        )

    def export_blog_label_training_parquet(self) -> tuple[bytes, dict[str, Any]]:
        status = self.sync_blog_label_training_parquet()
        parquet_path = Path(status["path"])
        return parquet_path.read_bytes(), status

    def create_blog_label_tag(self, *, name: str) -> dict[str, Any]:
        normalized_name = _normalize_catalog_text(name)
        if normalized_name is None:
            raise ValueError("Unsupported blog label name")
        slug = slugify_blog_label(normalized_name)
        with session_scope(self.session_factory) as session:
            existing = session.scalar(select(BlogLabelTagModel).where(BlogLabelTagModel.slug == slug).limit(1))
            if existing is not None:
                return _label_tag_payload_from_model(existing)
            timestamp = now_utc()
            if slug in BLOG_LABEL_NAME_TO_ID:
                tag = BlogLabelTagModel(
                    id=BLOG_LABEL_NAME_TO_ID[slug],
                    name=slug,
                    slug=slug,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            else:
                tag = BlogLabelTagModel(
                    name=normalized_name,
                    slug=slug,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            session.add(tag)
            session.flush()
            return _label_tag_payload_from_model(tag)

    def replace_blog_link_labels(
        self,
        *,
        blog_id: int,
        tag_ids: list[int] | None = None,
        label_id: dict[str, int] | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        if label_id is not None:
            label_counts = _normalize_label_counts(label_id)
        else:
            label_counts = _label_counts_from_tag_ids(tag_ids)
        with session_scope(self.session_factory) as session:
            label_names_by_id = _blog_label_names_by_id(session)
            unknown_ids = [int(key) for key in label_counts if int(key) not in label_names_by_id]
            if unknown_ids:
                raise ValueError("Unsupported blog label id")
            raw = session.scalar(
                select(RawDiscoveredUrlModel)
                .where(
                    self._labelable_raw_url_condition(),
                    RawDiscoveredUrlModel.id == blog_id,
                )
                .limit(1)
            )
            if raw is None:
                if self._get_blog_by_business_id(session, blog_id) is not None:
                    raise BlogLabelingConflictError("blog_labeling_requires_labelable_raw_url")
                raise BlogLabelingNotFoundError("blog_not_found")
            timestamp = now_utc()
            persisted_title = session.scalar(
                select(BlogModel.title).where(BlogModel.normalized_url == raw.normalized_url).limit(1)
            )
            display_title = str(title or "").strip() or str(persisted_title or "").strip() or None
            label_row = self._ensure_blog_label_row(
                session,
                normalized_url=str(raw.normalized_url),
                title=display_title,
            )
            label_row.label_id = label_counts
            label_row.updated_time = timestamp
            session.flush()
            return _BlogLabelStateView.from_assignment_rows(
                blog_id=int(raw.id),
                label_counts=label_row.label_id,
                last_labeled_at=timestamp if label_row.label_id else None,
                label_names=label_names_by_id,
            ).as_payload()

    def increment_blog_user_label(
        self,
        *,
        blog_id: int,
        label: str,
        previous_label: str | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """Apply one page-local public random-page label selection for a blog.

        Args:
            blog_id: Public/business blog ID from the catalog card.
            label: Label name, slug, or numeric ID. Only the four random-page
                labels (`blog`, `company`, `other`, `unknown`) are accepted.
            previous_label: Optional previous page selection to decrement when
                switching to a different label.
            user_id: Optional registered user ID. When present, the repository
                stores one current selection per user and URL, making label
                changes idempotent across browser refreshes.

        Returns:
            Updated label-state payload backed by ``blog_labels_userlabel``.
        """

        with session_scope(self.session_factory) as session:
            label_names_by_id = _blog_label_names_by_id(session)
            label_id = _label_id_from_name_in_session(session, label)
            label_slug = slugify_blog_label(label_names_by_id.get(label_id, str(label_id)))
            if label_slug not in RANDOM_BLOG_LABEL_SLUGS:
                raise ValueError("Unsupported random blog label")
            previous_label_id: int | None = None
            if previous_label is not None:
                previous_label_id = _label_id_from_name_in_session(session, previous_label)
                previous_label_slug = slugify_blog_label(
                    label_names_by_id.get(previous_label_id, str(previous_label_id))
                )
                if previous_label_slug not in RANDOM_BLOG_LABEL_SLUGS:
                    raise ValueError("Unsupported random blog label")
            blog = self._get_blog_by_business_id(session, blog_id)
            if blog is None:
                raise BlogLabelingNotFoundError("blog_not_found")
            if blog.crawl_status != CrawlStatus.FINISHED:
                raise BlogLabelingConflictError("blog_user_labeling_requires_finished_blog")
            timestamp = now_utc()
            existing_selection: BlogUserLabelSelectionModel | None = None
            if user_id is not None:
                if session.scalar(select(UserModel.id).where(UserModel.id == user_id).limit(1)) is None:
                    raise UserAuthError("user_not_found")
                existing_selection = session.scalar(
                    select(BlogUserLabelSelectionModel)
                    .where(
                        BlogUserLabelSelectionModel.user_id == user_id,
                        BlogUserLabelSelectionModel.normalized_url == blog.normalized_url,
                    )
                    .limit(1)
                )
                if existing_selection is not None:
                    previous_label_id = int(existing_selection.label_id)
            label_row = self._ensure_blog_user_label_row(
                session,
                normalized_url=str(blog.normalized_url),
                title=blog.title or blog.domain,
            )
            label_counts = _normalize_label_counts(label_row.label_id)
            label_key = str(label_id)
            if previous_label_id == label_id:
                return _BlogLabelStateView.from_assignment_rows(
                    blog_id=int(_business_blog_id(blog)),
                    label_counts=label_counts,
                    last_labeled_at=label_row.updated_time,
                    label_names=label_names_by_id,
                ).as_payload()
            if previous_label_id is not None and previous_label_id != label_id:
                previous_key = str(previous_label_id)
                previous_count = int(label_counts.get(previous_key, 0))
                if previous_count > 1:
                    label_counts[previous_key] = previous_count - 1
                else:
                    label_counts.pop(previous_key, None)
            label_counts[label_key] = int(label_counts.get(label_key, 0)) + 1
            label_row.label_id = label_counts
            label_row.updated_time = timestamp
            if user_id is not None:
                if existing_selection is None:
                    session.add(
                        BlogUserLabelSelectionModel(
                            user_id=user_id,
                            normalized_url=str(blog.normalized_url),
                            label_id=label_id,
                            created_at=timestamp,
                            updated_at=timestamp,
                        )
                    )
                else:
                    existing_selection.label_id = label_id
                    existing_selection.updated_at = timestamp
            session.flush()
            return _BlogLabelStateView.from_assignment_rows(
                blog_id=int(_business_blog_id(blog)),
                label_counts=label_row.label_id,
                last_labeled_at=timestamp,
                label_names=label_names_by_id,
            ).as_payload()

    def list_user_label_selections(self, *, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent random-page label selections made by one user.

        Args:
            user_id: Registered user identifier.
            limit: Maximum number of recent selections to return.

        Returns:
            Recent selections joined to current blog metadata when available.
        """

        resolved_limit = max(1, min(int(limit), 100))
        with session_scope(self.session_factory) as session:
            label_names_by_id = _blog_label_names_by_id(session)
            rows = session.execute(
                select(BlogUserLabelSelectionModel, BlogModel)
                .outerjoin(BlogModel, BlogModel.normalized_url == BlogUserLabelSelectionModel.normalized_url)
                .where(BlogUserLabelSelectionModel.user_id == user_id)
                .order_by(BlogUserLabelSelectionModel.updated_at.desc(), BlogUserLabelSelectionModel.id.desc())
                .limit(resolved_limit)
            ).all()
            items: list[dict[str, Any]] = []
            for selection, blog in rows:
                label_name = label_names_by_id.get(int(selection.label_id), str(selection.label_id))
                blog_view = _BlogPayloadView.from_model(blog)
                items.append(
                    {
                        "id": int(selection.id),
                        "normalized_url": selection.normalized_url,
                        "label_id": int(selection.label_id),
                        "label": slugify_blog_label(label_name),
                        "label_name": label_name,
                        "created_at": _iso(selection.created_at),
                        "updated_at": _iso(selection.updated_at),
                        "blog": blog_view.as_blog_payload() if blog_view is not None else None,
                    }
                )
            return items

    def count_user_label_selections(self, *, user_id: int) -> int:
        """Return the number of current random-page label choices made by one user.

        Args:
            user_id: Registered user identifier.

        Returns:
            Count of the user's current per-URL label selections.
        """

        with session_scope(self.session_factory) as session:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(BlogUserLabelSelectionModel)
                    .where(BlogUserLabelSelectionModel.user_id == user_id)
                )
                or 0
            )

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

            return {
                **self._row_blog_payload(blog_row),
                "discovery_path": self._blog_discovery_path_payload(session, blog_row[0]),
                "relation_graphs": {
                    "incoming": self._blog_relation_graph_payload(
                        session,
                        blog=blog_row[0],
                        direction="incoming",
                    ),
                    "outgoing": self._blog_relation_graph_payload(
                        session,
                        blog=blog_row[0],
                        direction="outgoing",
                    ),
                },
                "incoming_edges": self._blog_detail_relation_payloads(
                    session,
                    incoming_edges,
                    neighbor_id_getter=lambda edge: int(edge.from_blog_id),
                ),
                "outgoing_edges": self._blog_detail_relation_payloads(
                    session,
                    outgoing_edges,
                    neighbor_id_getter=lambda edge: int(edge.to_blog_id),
                ),
                "recommended_blogs": self._recommended_blog_rows(session, recommendation_map),
            }

    def list_edges(self) -> list[dict[str, Any]]:
        with session_scope(self.session_factory) as session:
            return self._ordered_row_payloads(
                session,
                statement=select(EdgeModel).order_by(EdgeModel.id.asc()),
                serializer=_edge_payload,
            )

    def list_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        return []

    def stats(self) -> dict[str, Any]:
        with session_scope(self.session_factory) as session:
            rows = session.execute(
                select(BlogModel.crawl_status, func.count()).group_by(BlogModel.crawl_status)
            ).all()
            status_counts = {str(status.value): int(count) for status, count in rows}
            total_blogs = _count_selectable_rows(session, BlogModel)
            total_edges = _count_selectable_rows(session, EdgeModel)
            raw_discovered_urls = _count_selectable_rows(session, RawDiscoveredUrlModel)
            average_friend_links = float(session.scalar(select(func.avg(BlogModel.friend_links_count))) or 0.0)
            return {
                "total_blogs": total_blogs,
                "total_edges": total_edges,
                "raw_discovered_urls": raw_discovered_urls,
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
            total_raw = _count_selectable_rows(session, RawDiscoveredUrlModel)
            total_blogs = _count_selectable_rows(session, BlogModel)
            grouped_rows = session.execute(
                select(RawDiscoveredUrlModel.status, func.count()).group_by(RawDiscoveredUrlModel.status)
            ).all()
            accepted_rows = session.execute(
                select(RawDiscoveredUrlModel.accepted_by, func.count())
                .where(RawDiscoveredUrlModel.status == RAW_DISCOVERED_URL_SUCCESS_STATUS)
                .group_by(RawDiscoveredUrlModel.accepted_by)
            ).all()
        counts_by_status = {str(status): int(count) for status, count in grouped_rows}
        success_count = counts_by_status.get(RAW_DISCOVERED_URL_SUCCESS_STATUS, 0)
        success_sources = {
            "rss": 0,
            "model": 0,
            "unknown": 0,
        }
        for accepted_by, count in accepted_rows:
            source = str(accepted_by or "").strip().lower() or "unknown"
            success_sources[source] = success_sources.get(source, 0) + int(count)

        remaining = total_raw
        by_filter_reason: dict[str, int] = {"raw": total_raw}
        rule_drops: dict[str, int] = {}
        after_rules = total_raw
        for status in decision_chain.ordered_statuses():
            dropped = counts_by_status.get(status, 0)
            remaining -= dropped
            by_filter_reason[status] = max(remaining, 0)
            if status.startswith("rule:"):
                rule_drops[status] = dropped
                after_rules = max(remaining, 0)

        # Terminal nodes: the chain loop above only subtracts the rejecting
        # statuses, so close the funnel with the real accepted-URL count and the
        # blog count it produces. ``success`` -> ``blogs`` differ by the URLs
        # that ``upsert_blog`` merges into an existing site via identity_key.
        by_filter_reason[RAW_DISCOVERED_URL_SUCCESS_STATUS] = success_count
        by_filter_reason["blogs"] = total_blogs

        # Reconcile: every raw URL is either accepted (success) or carries a
        # rejecting status. Any leftover means an unaccounted status slipped
        # past the chain ordering, so surface it instead of hiding the gap.
        rejected_total = sum(
            count for status, count in counts_by_status.items() if status != RAW_DISCOVERED_URL_SUCCESS_STATUS
        )
        unaccounted = total_raw - success_count - rejected_total
        if unaccounted:
            LOGGER.warning(
                "filter_stats unaccounted raw URLs: total=%s success=%s rejected=%s unaccounted=%s",
                total_raw,
                success_count,
                rejected_total,
                unaccounted,
            )
            by_filter_reason["other"] = unaccounted
        funnel = {
            "raw": total_raw,
            "after_rules": after_rules,
            "model_rejected": counts_by_status.get("model:model_consensus_all_non_blog", 0),
            "success": success_count,
            "blogs": total_blogs,
        }
        return {
            "by_filter_reason": by_filter_reason,
            "rule_drops": rule_drops,
            "success_sources": success_sources,
            "funnel": funnel,
        }

    def create_blog_dedup_scan_run(self, *, crawler_was_running: bool = False) -> dict[str, Any]:
        started_at = now_utc()
        settings = self._decision_scan_settings()
        with session_scope(self.session_factory) as session:
            total_count = _count_selectable_rows(session, BlogModel)
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
                run = self._require_model(
                    session,
                    BlogDedupScanRunModel,
                    run_id,
                    not_found_error="blog_dedup_scan_run_not_found",
                )
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
                    run = self._require_model(
                        session,
                        BlogDedupScanRunModel,
                        run_id,
                        not_found_error="blog_dedup_scan_run_not_found",
                    )
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
                run = self._require_model(
                    session,
                    BlogDedupScanRunModel,
                    run_id,
                    not_found_error="blog_dedup_scan_run_not_found",
                )
                completed_at = now_utc()
                final_blog_count = _count_selectable_rows(session, BlogModel)
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
            run = self._require_model(
                session,
                BlogDedupScanRunModel,
                run_id,
                not_found_error="blog_dedup_scan_run_not_found",
            )
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
            return self._latest_row_payload(
                session,
                statement=select(BlogDedupScanRunModel).order_by(BlogDedupScanRunModel.id.desc()).limit(1),
                serializer=_blog_dedup_scan_run_payload,
            )

    def list_blog_dedup_scan_run_items(self, run_id: int) -> list[dict[str, Any]]:
        with session_scope(self.session_factory) as session:
            return self._ordered_row_payloads(
                session,
                statement=(
                    select(BlogDedupScanRunItemModel)
                    .where(BlogDedupScanRunItemModel.run_id == run_id)
                    .order_by(BlogDedupScanRunItemModel.id.asc())
                ),
                serializer=_blog_dedup_scan_run_item_payload,
            )

    def reset(self) -> dict[str, Any]:
        with session_scope(self.session_factory) as session:
            blogs_deleted = _count_selectable_rows(session, BlogModel)
            edges_deleted = _count_selectable_rows(session, EdgeModel)
            requests_deleted = _count_selectable_rows(session, IngestionRequestModel)
            users_preserved = _count_selectable_rows(session, UserModel)
            user_sessions_preserved = _count_selectable_rows(session, UserSessionModel)
            labels_preserved = _count_selectable_rows(session, BlogLabelModel)
            user_labels_preserved = _count_selectable_rows(session, BlogUserLabelModel)
            user_label_selections_preserved = _count_selectable_rows(session, BlogUserLabelSelectionModel)
            label_tags_preserved = _count_selectable_rows(session, BlogLabelTagModel)
            seeds_preserved = _count_selectable_rows(session, SeedModel)
            raw_urls_deleted = _count_selectable_rows(session, RawDiscoveredUrlModel)
            recommendation_interactions_deleted = _count_selectable_rows(session, BlogInteractionModel)
            recommendation_impressions_deleted = _count_selectable_rows(session, RecommendationImpressionModel)
            recommendation_requests_deleted = _count_selectable_rows(session, RecommendationRequestModel)
            scan_items_deleted = _count_selectable_rows(session, BlogDedupScanRunItemModel)
            scan_runs_deleted = _count_selectable_rows(session, BlogDedupScanRunModel)
            session.query(SeedModel).update({SeedModel.blog_id: None})
            session.query(BlogInteractionModel).delete()
            session.query(RecommendationImpressionModel).delete()
            session.query(RecommendationRequestModel).delete()
            session.query(BlogDedupScanRunItemModel).delete()
            session.query(BlogDedupScanRunModel).delete()
            session.query(RawDiscoveredUrlModel).delete()
            session.query(IngestionRequestModel).delete()
            session.query(EdgeModel).delete()
            session.query(BlogModel).delete()
            return {
                "ok": True,
                "blogs_deleted": blogs_deleted,
                "edges_deleted": edges_deleted,
                "logs_deleted": 0,
                "ingestion_requests_deleted": requests_deleted,
                "users_preserved": users_preserved,
                "user_sessions_preserved": user_sessions_preserved,
                "blog_link_labels_deleted": 0,
                "blog_label_tags_deleted": 0,
                "blog_labels_preserved": labels_preserved,
                "blog_labels_userlabel_preserved": user_labels_preserved,
                "blog_user_label_selections_preserved": user_label_selections_preserved,
                "blog_label_subjects_preserved": 0,
                "blog_link_labels_preserved": labels_preserved,
                "blog_label_tags_preserved": label_tags_preserved,
                "seeds_preserved": seeds_preserved,
                "raw_discovered_urls_deleted": raw_urls_deleted,
                "recommendation_interactions_deleted": recommendation_interactions_deleted,
                "recommendation_impressions_deleted": recommendation_impressions_deleted,
                "recommendation_requests_deleted": recommendation_requests_deleted,
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
            return SQLAlchemyRepository(db_dsn, decision_settings=settings, startup_schema_sync=True)
        except ModuleNotFoundError as exc:
            if exc.name != "psycopg":
                raise
    return Repository(db_path, decision_settings=settings)
