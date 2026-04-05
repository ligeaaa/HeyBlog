"""SQLAlchemy-backed persistence repository."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from typing import Any
from typing import Protocol

from sqlalchemy import func
from sqlalchemy import text
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy.orm import Session

from persistence_api.db import create_persistence_engine
from persistence_api.db import create_session_factory
from persistence_api.db import session_scope
from persistence_api.models import Base
from persistence_api.models import BlogModel
from persistence_api.models import EdgeModel
from shared.contracts.enums import CrawlStatus

BLOG_CATALOG_ALLOWED_STATUSES = frozenset({status.value for status in CrawlStatus})
BLOG_CATALOG_DEFAULT_PAGE_SIZE = 50
BLOG_CATALOG_MAX_PAGE_SIZE = 200
BLOG_CATALOG_SORT = "id_desc"


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


def normalize_blog_catalog_query(
    *,
    page: int = 1,
    page_size: int = BLOG_CATALOG_DEFAULT_PAGE_SIZE,
    site: str | None = None,
    url: str | None = None,
    status: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    """Normalize catalog query params into one shared spec."""
    normalized_status = _normalize_catalog_text(status)
    if normalized_status is not None:
        normalized_status = normalized_status.upper()
        if normalized_status not in BLOG_CATALOG_ALLOWED_STATUSES:
            raise ValueError(f"Unsupported crawl status: {normalized_status}")

    return {
        "page": max(page, 1),
        "page_size": max(1, min(page_size, BLOG_CATALOG_MAX_PAGE_SIZE)),
        "site": _normalize_catalog_text(site),
        "url": _normalize_catalog_text(url),
        "status": normalized_status,
        "q": _normalize_catalog_text(q),
        "sort": BLOG_CATALOG_SORT,
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
        "sort": BLOG_CATALOG_SORT,
    }


def _blog_payload(model: BlogModel) -> dict[str, Any]:
    return {
        "id": int(model.id),
        "url": model.url,
        "normalized_url": model.normalized_url,
        "domain": model.domain,
        "title": model.title,
        "icon_url": model.icon_url,
        "status_code": model.status_code,
        "crawl_status": model.crawl_status.value,
        "friend_links_count": int(model.friend_links_count),
        "last_crawled_at": _iso(model.last_crawled_at),
        "created_at": _iso(model.created_at),
        "updated_at": _iso(model.updated_at),
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


def _neighbor_payload(model: BlogModel | None) -> dict[str, Any] | None:
    if model is None:
        return None
    return {
        "id": int(model.id),
        "domain": model.domain,
        "title": model.title,
        "icon_url": model.icon_url,
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
            rows = session.scalars(select(BlogModel).order_by(BlogModel.id.asc())).all()
            return [_blog_payload(row) for row in rows]

    def list_blogs_catalog(
        self,
        *,
        page: int = 1,
        page_size: int = BLOG_CATALOG_DEFAULT_PAGE_SIZE,
        site: str | None = None,
        url: str | None = None,
        status: str | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        query = normalize_blog_catalog_query(
            page=page,
            page_size=page_size,
            site=site,
            url=url,
            status=status,
            q=q,
        )
        with session_scope(self.session_factory) as session:
            statement = select(BlogModel)
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
                statement = statement.where(BlogModel.crawl_status == CrawlStatus(query["status"]))
            if query["q"] is not None:
                pattern = f"%{query['q']}%"
                statement = statement.where(
                    or_(
                        BlogModel.title.ilike(pattern),
                        BlogModel.domain.ilike(pattern),
                        BlogModel.url.ilike(pattern),
                    )
                )

            total_items = int(session.scalar(select(func.count()).select_from(statement.subquery())) or 0)
            total_pages = ceil(total_items / query["page_size"]) if total_items else 0
            effective_page = 1 if total_pages == 0 else min(query["page"], total_pages)
            offset = (effective_page - 1) * query["page_size"]
            rows = session.scalars(
                statement.order_by(BlogModel.id.desc()).limit(query["page_size"]).offset(offset)
            ).all()
            return _catalog_response(
                items=[_blog_payload(row) for row in rows],
                page=effective_page,
                page_size=query["page_size"],
                total_items=total_items,
                filters={
                    "q": query["q"],
                    "site": query["site"],
                    "url": query["url"],
                    "status": query["status"],
                },
            )

    def get_blog(self, blog_id: int) -> dict[str, Any] | None:
        with session_scope(self.session_factory) as session:
            blog = session.get(BlogModel, blog_id)
            return _blog_payload(blog) if blog is not None else None

    def get_blog_detail(self, blog_id: int) -> dict[str, Any] | None:
        with session_scope(self.session_factory) as session:
            blog = session.get(BlogModel, blog_id)
            if blog is None:
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

            return {
                **_blog_payload(blog),
                "incoming_edges": [
                    relation_payload(edge, neighbor_id=int(edge.from_blog_id)) for edge in incoming_edges
                ],
                "outgoing_edges": [
                    relation_payload(edge, neighbor_id=int(edge.to_blog_id)) for edge in outgoing_edges
                ],
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
