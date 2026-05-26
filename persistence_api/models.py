"""SQLAlchemy ORM models for persistence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import JSON
from sqlalchemy import Index
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from shared.contracts.enums import CrawlStatus


class Base(DeclarativeBase):
    """Shared declarative base."""


class BlogModel(Base):
    """Blog node persisted in the crawl graph.

    Args:
        None. SQLAlchemy constructs model instances from mapped keyword
        arguments.

    Returns:
        Blog database row whose public/business identifier is ``blog_id``.
    """

    __tablename__ = "blogs"

    id: Mapped[int] = mapped_column(primary_key=True)
    blog_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    identity_key: Mapped[str] = mapped_column(Text, nullable=False, index=True, default="")
    identity_reason_codes: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    identity_ruleset_version: Mapped[str] = mapped_column(Text, nullable=False, default="")
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crawl_status: Mapped[CrawlStatus] = mapped_column(
        Enum(CrawlStatus, name="crawl_status"),
        nullable=False,
        default=CrawlStatus.WAITING,
    )
    friend_links_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class IngestionRequestModel(Base):
    """User-triggered priority ingestion request."""

    __tablename__ = "ingestion_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    requested_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    identity_key: Mapped[str] = mapped_column(Text, nullable=False, index=True, default="")
    identity_reason_codes: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    identity_ruleset_version: Mapped[str] = mapped_column(Text, nullable=False, default="")
    requester_email: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    seed_blog_id: Mapped[int | None] = mapped_column(ForeignKey("blogs.blog_id", ondelete="SET NULL"), nullable=True)
    matched_blog_id: Mapped[int | None] = mapped_column(ForeignKey("blogs.blog_id", ondelete="SET NULL"), nullable=True)
    request_token: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BlogLabelModel(Base):
    """Stable URL-keyed label vote counters.

    Args:
        None. SQLAlchemy constructs model instances from mapped keyword
        arguments.

    Returns:
        One row per normalized URL. ``title`` stores the labeling-time display
        title, and ``label_id`` stores a JSON object whose string keys are
        label IDs and integer values are vote/count totals.
    """

    __tablename__ = "blog_labels"

    normalized_url: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    label_id: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False, default=dict)
    created_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BlogUserLabelModel(Base):
    """Public random-page URL-keyed label vote counters.

    Args:
        None. SQLAlchemy constructs model instances from mapped keyword
        arguments.

    Returns:
        One row per normalized URL. The table mirrors ``blog_labels`` but
        stores public random-page feedback so training labels remain unchanged.
    """

    __tablename__ = "blog_labels_userlabel"

    normalized_url: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    label_id: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False, default=dict)
    created_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BlogLabelTagModel(Base):
    """Label definition row used to resolve stored label IDs.

    Args:
        None. SQLAlchemy constructs model instances from mapped keyword
        arguments.

    Returns:
        A stable label definition whose ``id`` is used as the JSON key inside
        ``BlogLabelModel.label_id``.
    """

    __tablename__ = "blog_label_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class EdgeModel(Base):
    """Directed blog edge."""

    __tablename__ = "edges"
    __table_args__ = (UniqueConstraint("from_blog_id", "to_blog_id", name="uq_edges_from_to"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    from_blog_id: Mapped[int] = mapped_column(ForeignKey("blogs.blog_id", ondelete="CASCADE"), nullable=False)
    to_blog_id: Mapped[int] = mapped_column(ForeignKey("blogs.blog_id", ondelete="CASCADE"), nullable=False)
    link_url_raw: Mapped[str] = mapped_column(Text, nullable=False)
    link_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class RawDiscoveredUrlModel(Base):
    """One normalized URL observed by crawler candidate extraction."""

    __tablename__ = "raw_discovered_urls"
    __table_args__ = (
        Index("ix_raw_discovered_urls_status_id", "status", "id"),
        Index("ix_raw_discovered_urls_status_normalized_url_id", "status", "normalized_url", "id"),
        Index("ix_raw_discovered_urls_normalized_url_id", "normalized_url", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_blog_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BlogDedupScanRunModel(Base):
    """Administrative full-library dedup scan summary."""

    __tablename__ = "blog_dedup_scan_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    ruleset_version: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scanned_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    removed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kept_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    crawler_was_running: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    crawler_restart_attempted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    crawler_restart_succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    search_reindexed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BlogDedupScanRunItemModel(Base):
    """Detailed removal records produced by one dedup scan run."""

    __tablename__ = "blog_dedup_scan_run_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("blog_dedup_scan_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    survivor_blog_id: Mapped[int] = mapped_column(
        ForeignKey("blogs.blog_id", ondelete="SET NULL"),
        nullable=True,
    )
    removed_blog_id: Mapped[int | None] = mapped_column(nullable=True)
    survivor_identity_key: Mapped[str] = mapped_column(Text, nullable=False)
    removed_url: Mapped[str] = mapped_column(Text, nullable=False)
    removed_normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    removed_domain: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    reason_codes: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    survivor_selection_basis: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class UrlRefilterRunModel(Base):
    """Administrative URL refilter run summary."""

    __tablename__ = "url_refilter_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    filter_chain_version: Mapped[str] = mapped_column(Text, nullable=False, default="")
    crawler_was_running: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    backup_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scanned_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deactivated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retagged_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_raw_url_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class UrlRefilterRunEventModel(Base):
    """Timestamped event log for one URL refilter run."""

    __tablename__ = "url_refilter_run_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("url_refilter_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
