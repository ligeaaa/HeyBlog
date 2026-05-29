"""Add blog business-key schema for existing databases.

Revision ID: 20260423_02
Revises: 20260423_01
Create Date: 2026-04-23 11:30:38 BST
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260423_02"
down_revision = "20260423_01"
branch_labels = None
depends_on = None


BLOG_FK_REWRITES = (
    ("edges", "edges_from_blog_id_fkey", "from_blog_id", "CASCADE"),
    ("edges", "edges_to_blog_id_fkey", "to_blog_id", "CASCADE"),
    ("ingestion_requests", "ingestion_requests_seed_blog_id_fkey", "seed_blog_id", "SET NULL"),
    ("ingestion_requests", "ingestion_requests_matched_blog_id_fkey", "matched_blog_id", "SET NULL"),
    ("blog_label_assignments", "blog_label_assignments_blog_id_fkey", "blog_id", "CASCADE"),
    ("blog_dedup_scan_run_items", "blog_dedup_scan_run_items_survivor_blog_id_fkey", "survivor_blog_id", "SET NULL"),
)


def _table_names() -> set[str]:
    """Return the current database table names."""
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    """Return column names for one table."""
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    """Return index names for one table."""
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _unique_constraint_names_for_columns(table_name: str, column_names: list[str]) -> set[str]:
    """Return unique constraint names matching the provided columns."""
    expected = tuple(column_names)
    return {
        constraint["name"]
        for constraint in sa.inspect(op.get_bind()).get_unique_constraints(table_name)
        if constraint["name"] and tuple(constraint.get("column_names") or ()) == expected
    }


def _has_unique_constraint(table_name: str, column_names: list[str]) -> bool:
    """Return whether a table already has a unique constraint over the columns."""
    expected = tuple(column_names)
    return any(
        tuple(constraint.get("column_names") or ()) == expected
        for constraint in sa.inspect(op.get_bind()).get_unique_constraints(table_name)
    )


def _foreign_key_names(table_name: str) -> set[str]:
    """Return foreign-key constraint names for one table."""
    return {
        constraint["name"]
        for constraint in sa.inspect(op.get_bind()).get_foreign_keys(table_name)
        if constraint["name"]
    }


def upgrade() -> None:
    """Migrate old id-based blog references to the current business-key schema."""
    bind = op.get_bind()
    tables = _table_names()
    if "blogs" not in tables:
        return

    if "blog_id" not in _column_names("blogs"):
        op.add_column("blogs", sa.Column("blog_id", sa.Integer(), nullable=True))
        bind.execute(sa.text("UPDATE blogs SET blog_id = id WHERE blog_id IS NULL"))

    if bind.dialect.name == "sqlite" and "uq_blogs_blog_id" not in _index_names("blogs"):
        op.create_index("uq_blogs_blog_id", "blogs", ["blog_id"], unique=True)
    elif bind.dialect.name != "sqlite" and not _has_unique_constraint("blogs", ["blog_id"]):
        op.create_unique_constraint("uq_blogs_blog_id", "blogs", ["blog_id"])

    if "ix_blogs_blog_id" not in _index_names("blogs"):
        op.create_index("ix_blogs_blog_id", "blogs", ["blog_id"])

    if bind.dialect.name != "sqlite":
        for table_name, constraint_name, column_name, ondelete in BLOG_FK_REWRITES:
            if table_name not in tables or column_name not in _column_names(table_name):
                continue
            foreign_keys = _foreign_key_names(table_name)
            if constraint_name in foreign_keys:
                op.drop_constraint(constraint_name, table_name, type_="foreignkey")
            op.create_foreign_key(
                constraint_name,
                table_name,
                "blogs",
                [column_name],
                ["blog_id"],
                ondelete=ondelete,
            )

    tables = _table_names()
    if "raw_discovered_urls" not in tables:
        op.create_table(
            "raw_discovered_urls",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_blog_id", sa.Integer(), nullable=False),
            sa.Column("normalized_url", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["source_blog_id"], ["blogs.blog_id"], ondelete="CASCADE"),
        )
        op.create_index("ix_raw_discovered_urls_source_blog_id", "raw_discovered_urls", ["source_blog_id"])


def downgrade() -> None:
    """Revert the additive business-key migration."""
    bind = op.get_bind()
    tables = _table_names()

    if "raw_discovered_urls" in tables:
        op.drop_index("ix_raw_discovered_urls_source_blog_id", table_name="raw_discovered_urls")
        op.drop_table("raw_discovered_urls")

    if bind.dialect.name != "sqlite":
        for table_name, constraint_name, column_name, ondelete in BLOG_FK_REWRITES:
            if table_name not in tables or column_name not in _column_names(table_name):
                continue
            if constraint_name in _foreign_key_names(table_name):
                op.drop_constraint(constraint_name, table_name, type_="foreignkey")
            op.create_foreign_key(
                constraint_name,
                table_name,
                "blogs",
                [column_name],
                ["id"],
                ondelete=ondelete,
            )

    if "blogs" in tables:
        if "ix_blogs_blog_id" in _index_names("blogs"):
            op.drop_index("ix_blogs_blog_id", table_name="blogs")
        if "uq_blogs_blog_id" in _index_names("blogs"):
            op.drop_index("uq_blogs_blog_id", table_name="blogs")
        for constraint_name in _unique_constraint_names_for_columns("blogs", ["blog_id"]):
            op.drop_constraint(constraint_name, "blogs", type_="unique")
        if "blog_id" in _column_names("blogs"):
            op.drop_column("blogs", "blog_id")
