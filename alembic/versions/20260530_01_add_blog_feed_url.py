"""Add blogs.feed_url for discovered RSS/Atom feeds.

Revision ID: 20260530_01
Revises: 20260526_02
Create Date: 2026-05-30 13:30:00 BST
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260530_01"
down_revision = "20260526_02"
branch_labels = None
depends_on = None


def _blog_columns() -> set[str]:
    """Return column names currently present on the ``blogs`` table."""
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("blogs")}


def upgrade() -> None:
    """Add the nullable ``feed_url`` column used by RSS feed discovery."""
    if "feed_url" not in _blog_columns():
        op.add_column("blogs", sa.Column("feed_url", sa.Text(), nullable=True))


def downgrade() -> None:
    """Drop the ``feed_url`` column from ``blogs``."""
    if "feed_url" in _blog_columns():
        op.drop_column("blogs", "feed_url")
