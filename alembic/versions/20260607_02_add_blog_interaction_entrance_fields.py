"""Add entrance metadata columns to existing blog interaction tables.

Revision ID: 20260607_02
Revises: 20260607_01
Create Date: 2026-06-07 15:08:00 BST
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260607_02"
down_revision = "20260607_01"
branch_labels = None
depends_on = None


def _table_columns(table_name: str) -> set[str]:
    """Return current column names for one table.

    Args:
        table_name: Table to inspect.

    Returns:
        Set of column names currently present on the table.
    """

    inspector = sa.inspect(op.get_bind())
    if table_name not in set(inspector.get_table_names()):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    """Backfill entrance metadata columns added after the first event migration.

    Args:
        None.

    Returns:
        None. The active database schema is mutated in place.
    """

    columns = _table_columns("blog_interactions")
    if not columns:
        return
    if "entrance_kind" not in columns:
        op.add_column(
            "blog_interactions",
            sa.Column("entrance_kind", sa.Text(), nullable=False, server_default="legacy_unknown"),
        )
        op.alter_column("blog_interactions", "entrance_kind", server_default=None)
    if "entrance_url" not in columns:
        op.add_column(
            "blog_interactions",
            sa.Column("entrance_url", sa.Text(), nullable=False, server_default="legacy_unknown"),
        )
        op.alter_column("blog_interactions", "entrance_url", server_default=None)
    op.create_index(
        "ix_blog_interactions_entrance_kind",
        "blog_interactions",
        ["entrance_kind"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_blog_interactions_entrance_url",
        "blog_interactions",
        ["entrance_url"],
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop entrance metadata columns from blog interaction rows.

    Args:
        None.

    Returns:
        None. The active database schema is mutated in place.
    """

    columns = _table_columns("blog_interactions")
    if not columns:
        return
    op.drop_index("ix_blog_interactions_entrance_url", table_name="blog_interactions", if_exists=True)
    op.drop_index("ix_blog_interactions_entrance_kind", table_name="blog_interactions", if_exists=True)
    if "entrance_url" in columns:
        op.drop_column("blog_interactions", "entrance_url")
    if "entrance_kind" in columns:
        op.drop_column("blog_interactions", "entrance_kind")
