"""SQLAlchemy-backed persistence repository."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from typing import Any
from typing import Protocol
from urllib.parse import urlparse

from sqlalchemy import and_
from sqlalchemy import case
from sqlalchemy import cast
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy import String
from sqlalchemy import text
from sqlalchemy.orm import Session

from persistence_api.db import create_persistence_engine
from persistence_api.db import create_session_factory
from persistence_api.db import session_scope
from persistence_api.models import Base
from persistence_api.models import BlogModel
from persistence_api.models import EdgeModel
from persistence_api.recommendations import collect_friends_of_friends_candidates
from shared.contracts.enums import CrawlStatus

BLOG_CATALOG_ALLOWED_STATUSES = frozenset({status.value for status in CrawlStatus})
BLOG_CATALOG_DEFAULT_PAGE_SIZE = 50
BLOG_CATALOG_MAX_PAGE_SIZE = 200
BLOG_CATALOG_DEFAULT_SORT = "id_desc"
BLOG_CATALOG_ALLOWED_SORTS = frozenset(
    {"id_desc", "recent_activity", "connections", "recently_discovered"}
)


def now_utc() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


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
    q: str | None = None,
    sort: str = BLOG_CATALOG_DEFAULT_SORT,
    has_title: bool | str | None = None,
    has_icon: bool | str | None = None,
    min_connections: int | str | None = None,
) -> dict[str, Any]:
    """Normalize catalog query params into one shared spec."""
    normalized_status = _normalize_catalog_text(status)
    if normalized_status is not None:
        normalized_status = normalized_status.upper()
        if normalized_status not in BLOG_CATALOG_ALLOWED_STATUSES:
            raise ValueError(f"Unsupported crawl status: {normalized_status}")

    normalized_sort = _normalize_catalog_text(sort) or BLOG_CATALOG_DEFAULT_SORT
    if normalized_sort not in BLOG_CATALOG_ALLOWED_SORTS:
        raise ValueError(f"Unsupported blog catalog sort: {normalized_sort}")

    return {
        "page": max(page, 1),
        "page_size": max(1, min(page_size, BLOG_CATALOG_MAX_PAGE_SIZE)),
        "site": _normalize_catalog_text(site),
        "url": _normalize_catalog_text(url),
        "status": normalized_status,
        "q": _normalize_catalog_text(q),
        "sort": normalized_sort,
        "has_title": _normalize_catalog_bool(has_title),
        "has_icon": _normalize_catalog_bool(has_icon),
        "min_connections": _normalize_catalog_int(min_connections),
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
    return {
        "id": int(model.id),
        "url": model.url,
        "normalized_url": model.normalized_url,
        "domain": model.domain,
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
        "id": int(model.id),
        "domain": model.domain,
        "title": _resolved_blog_title(model),
        "icon_url": _resolved_blog_icon_url(model),
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
    ) -> tuple[int, bool]: ...

    def get_next_waiting_blog(self) -> dict[str, Any] | None: ...

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

    def list_blogs(self) -> list[dict[str, Any]]: ...

    def list_blogs_catalog(
        self,
        *,
        page: int = 1,
        page_size: int = BLOG_CATALOG_DEFAULT_PAGE_SIZE,
        site: str | None = None,
        url: str | None = None,
        status: str | None = None,
        q: str | None = None,
        sort: str = BLOG_CATALOG_DEFAULT_SORT,
        has_title: bool | str | None = None,
        has_icon: bool | str | None = None,
        min_connections: int | None = None,
    ) -> dict[str, Any]: ...

    def get_blog(self, blog_id: int) -> dict[str, Any] | None: ...

    def get_blog_detail(self, blog_id: int) -> dict[str, Any] | None: ...

    def list_edges(self) -> list[dict[str, Any]]: ...

    def list_logs(self, limit: int = 100) -> list[dict[str, Any]]: ...

    def stats(self) -> dict[str, Any]: ...

    def reset(self) -> dict[str, Any]: ...


@dataclass(slots=True)
class SQLAlchemyRepository:
    """Repository implemented with one SQLAlchemy engine."""

    database_url: str
    engine: Any = field(init=False, repr=False)
    session_factory: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.engine = create_persistence_engine(self.database_url)
        self.session_factory = create_session_factory(self.engine)
        Base.metadata.create_all(self.engine)
        with session_scope(self.session_factory) as session:
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
            .outerjoin(metrics["incoming_counts"], metrics["incoming_counts"].c.blog_id == BlogModel.id)
            .outerjoin(metrics["outgoing_counts"], metrics["outgoing_counts"].c.blog_id == BlogModel.id)
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
    ) -> tuple[int, bool]:
        with session_scope(self.session_factory) as session:
            existing = session.scalar(
                select(BlogModel).where(BlogModel.normalized_url == normalized_url)
            )
            if existing is not None:
                return int(existing.id), False

            blog = BlogModel(
                url=url,
                normalized_url=normalized_url,
                domain=domain,
                crawl_status=CrawlStatus.WAITING,
                friend_links_count=0,
                created_at=now_utc(),
                updated_at=now_utc(),
            )
            session.add(blog)
            session.flush()
            return int(blog.id), True

    def get_next_waiting_blog(self) -> dict[str, Any] | None:
        with session_scope(self.session_factory) as session:
            statement = (
                select(BlogModel)
                .where(BlogModel.crawl_status == CrawlStatus.WAITING)
                .order_by(BlogModel.id.asc())
                .limit(1)
            )
            if self.dialect_name == "postgresql":
                statement = statement.with_for_update(skip_locked=True)
            blog = session.scalar(statement)
            if blog is None:
                return None
            blog.crawl_status = CrawlStatus.PROCESSING
            blog.updated_at = now_utc()
            session.flush()
            return _blog_payload(blog)

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
            blog = session.get(BlogModel, blog_id)
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

    def list_blogs(self) -> list[dict[str, Any]]:
        with session_scope(self.session_factory) as session:
            statement, _ = self._blog_select()
            rows = session.execute(statement.order_by(BlogModel.id.asc())).all()
            return [self._row_blog_payload(row) for row in rows]

    def list_blogs_catalog(
        self,
        *,
        page: int = 1,
        page_size: int = BLOG_CATALOG_DEFAULT_PAGE_SIZE,
        site: str | None = None,
        url: str | None = None,
        status: str | None = None,
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
            if query["status"] is not None:
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
                statement = statement.where(BlogModel.domain != "")
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
                    metrics["activity_at"].desc(), metrics["connection_count"].desc(), BlogModel.id.desc()
                )
            elif query["sort"] == "connections":
                statement = statement.order_by(
                    metrics["connection_count"].desc(), metrics["activity_at"].desc(), BlogModel.id.desc()
                )
            elif query["sort"] == "recently_discovered":
                statement = statement.order_by(BlogModel.created_at.desc(), BlogModel.id.desc())
            else:
                statement = statement.order_by(BlogModel.id.desc())

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
                    "sort": query["sort"],
                    "has_title": query["has_title"],
                    "has_icon": query["has_icon"],
                    "min_connections": query["min_connections"],
                },
            )

    def get_blog(self, blog_id: int) -> dict[str, Any] | None:
        with session_scope(self.session_factory) as session:
            statement, _ = self._blog_select()
            row = session.execute(statement.where(BlogModel.id == blog_id)).first()
            return self._row_blog_payload(row) if row is not None else None

    def get_blog_detail(self, blog_id: int) -> dict[str, Any] | None:
        with session_scope(self.session_factory) as session:
            statement, _ = self._blog_select()
            blog_row = session.execute(statement.where(BlogModel.id == blog_id)).first()
            if blog_row is None:
                return None
            outgoing_edges = session.scalars(
                select(EdgeModel).where(EdgeModel.from_blog_id == blog_id).order_by(EdgeModel.id.asc())
            ).all()
            incoming_edges = session.scalars(
                select(EdgeModel).where(EdgeModel.to_blog_id == blog_id).order_by(EdgeModel.id.asc())
            ).all()

            def relation_payload(edge: EdgeModel, *, neighbor_id: int) -> dict[str, Any]:
                neighbor = session.get(BlogModel, neighbor_id)
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
                    recommended_statement.where(BlogModel.id.in_(recommendation_map.keys()))
                ).all()
                recommended_by_id = {int(row[0].id): row for row in recommended_blog_rows}
                via_blog_ids = {via_id for via_ids in recommendation_map.values() for via_id in via_ids}
                via_blogs = {
                    int(blog_model.id): blog_model
                    for blog_model in session.scalars(
                        select(BlogModel).where(BlogModel.id.in_(via_blog_ids))
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

    def reset(self) -> dict[str, Any]:
        with session_scope(self.session_factory) as session:
            blogs_deleted = int(session.scalar(select(func.count()).select_from(BlogModel)) or 0)
            edges_deleted = int(session.scalar(select(func.count()).select_from(EdgeModel)) or 0)
            if self.dialect_name == "postgresql":
                session.execute(text("TRUNCATE TABLE edges, blogs RESTART IDENTITY CASCADE"))
            else:
                session.query(EdgeModel).delete()
                session.query(BlogModel).delete()
            return {
                "ok": True,
                "blogs_deleted": blogs_deleted,
                "edges_deleted": edges_deleted,
                "logs_deleted": 0,
            }


class Repository(SQLAlchemyRepository):
    """Compatibility wrapper for test call sites that still pass a db path."""

    def __init__(self, db_path: Path) -> None:
        super().__init__(f"sqlite+pysqlite:///{db_path}")


def build_repository(*, db_path: Path, db_dsn: str | None = None) -> RepositoryProtocol:
    """Build the configured repository implementation."""
    if db_dsn is not None:
        return SQLAlchemyRepository(db_dsn)
    return Repository(db_path)
