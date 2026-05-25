"""Add raw URL indexes for admin labeling queries.

Revision ID: 20260525_03
Revises: 20260525_02
Create Date: 2026-05-25 22:40:00 BST
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260525_03"
down_revision = "20260525_02"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    """Return table names currently visible to Alembic."""
    return set(sa.inspect(op.get_bind()).get_table_names())


def _index_names(table_name: str) -> set[str]:
    """Return index names currently present on one table."""
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def upgrade() -> None:
    """Create indexes used by admin labeling candidate and export lookups."""
    if "raw_discovered_urls" not in _table_names():
        return
    indexes = _index_names("raw_discovered_urls")
    if "ix_raw_discovered_urls_status_id" not in indexes:
        op.create_index(
            "ix_raw_discovered_urls_status_id",
            "raw_discovered_urls",
            ["status", "id"],
        )
    if "ix_raw_discovered_urls_status_normalized_url_id" not in indexes:
        op.create_index(
            "ix_raw_discovered_urls_status_normalized_url_id",
            "raw_discovered_urls",
            ["status", "normalized_url", "id"],
        )
    if "ix_raw_discovered_urls_normalized_url_id" not in indexes:
        op.create_index(
            "ix_raw_discovered_urls_normalized_url_id",
            "raw_discovered_urls",
            ["normalized_url", "id"],
        )


def downgrade() -> None:
    """Drop raw URL labeling lookup indexes."""
    if "raw_discovered_urls" not in _table_names():
        return
    indexes = _index_names("raw_discovered_urls")
    if "ix_raw_discovered_urls_normalized_url_id" in indexes:
        op.drop_index("ix_raw_discovered_urls_normalized_url_id", table_name="raw_discovered_urls")
    if "ix_raw_discovered_urls_status_normalized_url_id" in indexes:
        op.drop_index("ix_raw_discovered_urls_status_normalized_url_id", table_name="raw_discovered_urls")
    if "ix_raw_discovered_urls_status_id" in indexes:
        op.drop_index("ix_raw_discovered_urls_status_id", table_name="raw_discovered_urls")
