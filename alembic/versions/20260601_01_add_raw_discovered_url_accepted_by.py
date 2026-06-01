"""Track accepted URL success source.

Revision ID: 20260601_01
Revises: 20260530_02
Create Date: 2026-06-01 16:13:39 BST
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260601_01"
down_revision = "20260530_02"
branch_labels = None
depends_on = None


def _raw_url_columns() -> set[str]:
    """Return column names currently present on ``raw_discovered_urls``."""
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("raw_discovered_urls")}


def upgrade() -> None:
    """Add nullable success-source attribution for future crawls."""
    if "accepted_by" not in _raw_url_columns():
        op.add_column("raw_discovered_urls", sa.Column("accepted_by", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove success-source attribution."""
    if "accepted_by" in _raw_url_columns():
        op.drop_column("raw_discovered_urls", "accepted_by")
