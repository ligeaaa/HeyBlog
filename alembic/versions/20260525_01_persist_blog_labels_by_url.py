"""Persist blog labels by stable normalized URL subjects.

Revision ID: 20260525_01
Revises: 20260423_02
Create Date: 2026-05-25 15:10:00 BST
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260525_01"
down_revision = "20260423_02"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    """Return table names currently present in the migration connection."""
    return set(sa.inspect(op.get_bind()).get_table_names())


def _foreign_key_names(table_name: str) -> set[str]:
    """Return named foreign keys currently present on one table."""
    return {
        constraint["name"]
        for constraint in sa.inspect(op.get_bind()).get_foreign_keys(table_name)
        if constraint["name"]
    }


def upgrade() -> None:
    """Move label assignments from run-local IDs to stable URL subjects."""
    bind = op.get_bind()
    tables = _table_names()
    if "blog_label_subjects" not in tables:
        op.create_table(
            "blog_label_subjects",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("normalized_url", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("normalized_url", name="uq_blog_label_subjects_normalized_url"),
        )
        op.create_index(
            "ix_blog_label_subjects_normalized_url",
            "blog_label_subjects",
            ["normalized_url"],
        )

    if "blog_label_assignments" not in tables:
        return

    rows = bind.execute(
        sa.text(
            "SELECT id, blog_id, tag_id, labeled_at, created_at, updated_at "
            "FROM blog_label_assignments ORDER BY id ASC"
        )
    ).mappings().all()
    for row in rows:
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

        subject_id = bind.execute(
            sa.text("SELECT id FROM blog_label_subjects WHERE normalized_url = :normalized_url"),
            {"normalized_url": normalized_url},
        ).scalar()
        if subject_id is None:
            bind.execute(
                sa.text(
                    "INSERT INTO blog_label_subjects (normalized_url, created_at, updated_at) "
                    "VALUES (:normalized_url, :created_at, :updated_at)"
                ),
                {
                    "normalized_url": normalized_url,
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                },
            )
            subject_id = bind.execute(
                sa.text("SELECT id FROM blog_label_subjects WHERE normalized_url = :normalized_url"),
                {"normalized_url": normalized_url},
            ).scalar()

        duplicate_id = bind.execute(
            sa.text(
                "SELECT id FROM blog_label_assignments "
                "WHERE blog_id = :subject_id AND tag_id = :tag_id AND id != :assignment_id"
            ),
            {
                "subject_id": subject_id,
                "tag_id": row["tag_id"],
                "assignment_id": row["id"],
            },
        ).scalar()
        if duplicate_id is not None:
            bind.execute(
                sa.text("DELETE FROM blog_label_assignments WHERE id = :assignment_id"),
                {"assignment_id": row["id"]},
            )
            continue

        bind.execute(
            sa.text("UPDATE blog_label_assignments SET blog_id = :subject_id WHERE id = :assignment_id"),
            {"subject_id": subject_id, "assignment_id": row["id"]},
        )

    if bind.dialect.name != "sqlite":
        for foreign_key in _foreign_key_names("blog_label_assignments"):
            op.drop_constraint(foreign_key, "blog_label_assignments", type_="foreignkey")
        op.create_foreign_key(
            "fk_blog_label_assignments_subject",
            "blog_label_assignments",
            "blog_label_subjects",
            ["blog_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    """Drop the URL subject table after removing dependent subject labels."""
    bind = op.get_bind()
    tables = _table_names()
    if "blog_label_assignments" in tables and bind.dialect.name != "sqlite":
        if "fk_blog_label_assignments_subject" in _foreign_key_names("blog_label_assignments"):
            op.drop_constraint(
                "fk_blog_label_assignments_subject",
                "blog_label_assignments",
                type_="foreignkey",
            )
    if "blog_label_subjects" in tables:
        op.drop_index("ix_blog_label_subjects_normalized_url", table_name="blog_label_subjects")
        op.drop_table("blog_label_subjects")
