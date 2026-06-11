"""Persist imported seed CSV rows in a dedicated table.

Revision ID: 20260606_01
Revises: 20260602_01
Create Date: 2026-06-06 16:27:56 BST
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260606_01"
down_revision = "20260602_01"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    """Return currently present database table names.

    Args:
        None.

    Returns:
        Set of table names currently present in the migration target.
    """

    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    """Create the durable seed import table.

    Args:
        None.

    Returns:
        None. The migration mutates the active database schema in place.
    """

    if "seeds" in _tables():
        return
    op.create_table(
        "seeds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("blog_id", sa.Integer(), sa.ForeignKey("blogs.blog_id", ondelete="SET NULL"), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("normalized_url", name="uq_seeds_normalized_url"),
    )
    op.create_index("ix_seeds_normalized_url", "seeds", ["normalized_url"])


def downgrade() -> None:
    """Drop the durable seed import table.

    Args:
        None.

    Returns:
        None. The migration mutates the active database schema in place.
    """

    if "seeds" not in _tables():
        return
    op.drop_index("ix_seeds_normalized_url", table_name="seeds")
    op.drop_table("seeds")
