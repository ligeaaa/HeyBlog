"""Add hourly admin statistics snapshots.

Revision ID: 20260611_02
Revises: 20260611_01
Create Date: 2026-06-11 00:00:00 BST
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260611_02"
down_revision = "20260611_01"
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
    """Create the hourly admin statistics snapshot table.

    Args:
        None.

    Returns:
        None. The migration mutates the active database schema in place.
    """

    if "admin_hourly_stats" in _tables():
        return
    op.create_table(
        "admin_hourly_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hour_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("random_request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("random_impression_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detail_open_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("external_open_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detail_ctr", sa.Float(), nullable=False, server_default="0"),
        sa.Column("external_ctr", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_click_ctr", sa.Float(), nullable=False, server_default="0"),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("hour_start", name="uq_admin_hourly_stats_hour_start"),
    )
    op.create_index("ix_admin_hourly_stats_hour_start", "admin_hourly_stats", ["hour_start"])


def downgrade() -> None:
    """Drop the hourly admin statistics snapshot table.

    Args:
        None.

    Returns:
        None. The migration mutates the active database schema in place.
    """

    if "admin_hourly_stats" in _tables():
        op.drop_table("admin_hourly_stats")
