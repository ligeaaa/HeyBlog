"""Collapse blog labels into one URL-keyed JSON table.

Revision ID: 20260525_02
Revises: 20260525_01
Create Date: 2026-05-25 16:20:00 BST
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260525_02"
down_revision = "20260525_01"
branch_labels = None
depends_on = None

DEFAULT_LABEL_TAGS = (
    (1, "blog"),
    (2, "company"),
    (3, "other"),
    (4, "unknown"),
    (5, "official"),
    (6, "government"),
)


def _table_names() -> set[str]:
    """Return table names currently visible to Alembic."""
    return set(sa.inspect(op.get_bind()).get_table_names())


def _normalize_counts(value: object) -> dict[str, int]:
    """Return positive integer label counts from raw JSON-like data."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    if not isinstance(value, dict):
        return {}
    counts: dict[str, int] = {}
    for key, count in value.items():
        try:
            resolved = int(count)
        except (TypeError, ValueError):
            continue
        if resolved > 0:
            counts[str(key)] = resolved
    return counts


def upgrade() -> None:
    """Create `blog_labels` and migrate old label structures into it."""
    bind = op.get_bind()
    tables = _table_names()
    if "blog_labels" not in tables:
        op.create_table(
            "blog_labels",
            sa.Column("normalized_url", sa.Text(), primary_key=True),
            sa.Column("title", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "label_id",
                sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
                nullable=False,
                server_default=sa.text("'{}'::jsonb") if bind.dialect.name == "postgresql" else sa.text("'{}'"),
            ),
            sa.Column("created_time", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_time", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_blog_labels_normalized_url", "blog_labels", ["normalized_url"])
    else:
        columns = {column["name"] for column in sa.inspect(bind).get_columns("blog_labels")}
        if "title" not in columns:
            op.add_column("blog_labels", sa.Column("title", sa.Text(), nullable=False, server_default=""))
    if "blog_label_tags" not in tables:
        op.create_table(
            "blog_label_tags",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("slug", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("slug", name="uq_blog_label_tags_slug"),
        )
        op.create_index("ix_blog_label_tags_slug", "blog_label_tags", ["slug"])
    for label_id, label_name in DEFAULT_LABEL_TAGS:
        if bind.dialect.name == "postgresql":
            bind.execute(
                sa.text(
                    "INSERT INTO blog_label_tags (id, name, slug) "
                    "VALUES (:id, :name, :slug) "
                    "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, slug = EXCLUDED.slug"
                ),
                {"id": label_id, "name": label_name, "slug": label_name},
            )
        else:
            bind.execute(
                sa.text(
                    "INSERT OR REPLACE INTO blog_label_tags (id, name, slug) "
                    "VALUES (:id, :name, :slug)"
                ),
                {"id": label_id, "name": label_name, "slug": label_name},
            )

    migrated: dict[str, dict[str, object]] = {}
    if "blog_label_assignments" in tables:
        rows = bind.execute(
            sa.text(
                "SELECT a.blog_id, a.tag_id, a.labeled_at, a.created_at, a.updated_at "
                "FROM blog_label_assignments a ORDER BY a.id ASC"
            )
        ).mappings().all()
        for row in rows:
            normalized_url = None
            if "blog_label_subjects" in tables:
                normalized_url = bind.execute(
                    sa.text("SELECT normalized_url FROM blog_label_subjects WHERE id = :subject_id"),
                    {"subject_id": row["blog_id"]},
                ).scalar()
            if normalized_url is None and "blogs" in tables:
                normalized_url = bind.execute(
                    sa.text("SELECT normalized_url FROM blogs WHERE blog_id = :blog_id"),
                    {"blog_id": row["blog_id"]},
                ).scalar()
            if normalized_url is None and "raw_discovered_urls" in tables:
                normalized_url = bind.execute(
                    sa.text("SELECT normalized_url FROM raw_discovered_urls WHERE id = :raw_id"),
                    {"raw_id": row["blog_id"]},
                ).scalar()
            if normalized_url is None:
                continue
            payload = migrated.setdefault(
                str(normalized_url),
                {"counts": {}, "created": row["created_at"], "updated": row["updated_at"]},
            )
            counts = payload["counts"]
            assert isinstance(counts, dict)
            label_key = str(row["tag_id"])
            counts[label_key] = int(counts.get(label_key, 0)) + 1
            payload["updated"] = row["updated_at"]

    for normalized_url, payload in migrated.items():
        existing = bind.execute(
            sa.text("SELECT label_id FROM blog_labels WHERE normalized_url = :normalized_url"),
            {"normalized_url": normalized_url},
        ).scalar()
        counts = _normalize_counts(existing)
        incoming = payload["counts"]
        assert isinstance(incoming, dict)
        for label_key, count in incoming.items():
            counts[str(label_key)] = int(counts.get(str(label_key), 0)) + int(count)
        title = ""
        if "blogs" in tables:
            title = str(
                bind.execute(
                    sa.text("SELECT title FROM blogs WHERE normalized_url = :normalized_url"),
                    {"normalized_url": normalized_url},
                ).scalar()
                or ""
            )
        if bind.dialect.name == "postgresql":
            bind.execute(
                sa.text(
                    "INSERT INTO blog_labels (normalized_url, title, label_id, created_time, updated_time) "
                    "VALUES (:normalized_url, :title, CAST(:label_id AS JSONB), :created_time, :updated_time) "
                    "ON CONFLICT (normalized_url) DO UPDATE "
                    "SET title = EXCLUDED.title, label_id = CAST(:label_id AS JSONB), updated_time = :updated_time"
                ),
                {
                    "normalized_url": normalized_url,
                    "title": title,
                    "label_id": json.dumps(counts),
                    "created_time": payload["created"],
                    "updated_time": payload["updated"],
                },
            )
        else:
            bind.execute(
                sa.text(
                    "INSERT OR REPLACE INTO blog_labels "
                    "(normalized_url, title, label_id, created_time, updated_time) "
                    "VALUES (:normalized_url, :title, :label_id, :created_time, :updated_time)"
                ),
                {
                    "normalized_url": normalized_url,
                    "title": title,
                    "label_id": json.dumps(counts),
                    "created_time": payload["created"],
                    "updated_time": payload["updated"],
                },
            )

    for table_name in ("blog_label_assignments", "blog_label_subjects"):
        if table_name in _table_names():
            op.drop_table(table_name)


def downgrade() -> None:
    """Drop the collapsed label table.

    The old three-table label structure is intentionally not recreated because
    the vote-count JSON representation cannot be losslessly mapped back to
    individual user assignments.
    """
    if "blog_labels" in _table_names():
        op.drop_index("ix_blog_labels_normalized_url", table_name="blog_labels")
        op.drop_table("blog_labels")
