"""SQLAlchemy ORM models for persistence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
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
    """Blog node persisted in the crawl graph."""

    __tablename__ = "blogs"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
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


class EdgeModel(Base):
    """Directed blog edge."""

    __tablename__ = "edges"
    __table_args__ = (UniqueConstraint("from_blog_id", "to_blog_id", name="uq_edges_from_to"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    from_blog_id: Mapped[int] = mapped_column(ForeignKey("blogs.id", ondelete="CASCADE"), nullable=False)
    to_blog_id: Mapped[int] = mapped_column(ForeignKey("blogs.id", ondelete="CASCADE"), nullable=False)
    link_url_raw: Mapped[str] = mapped_column(Text, nullable=False)
    link_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
