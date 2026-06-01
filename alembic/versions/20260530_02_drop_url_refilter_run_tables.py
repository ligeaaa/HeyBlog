"""Drop URL refilter run tracking tables.

The offline URL refilter feature was removed in favor of the live success-chain
(RSS discovery + model consensus). This migration drops the now-unused tables.

Revision ID: 20260530_02
Revises: 20260530_01
Create Date: 2026-05-30 13:45:00 BST
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260530_02"
down_revision = "20260530_01"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    """Return table names currently visible to Alembic."""
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    """Drop the URL refilter run and event tables when present."""
    existing_tables = _table_names()
    if "url_refilter_run_events" in existing_tables:
        op.drop_table("url_refilter_run_events")
    if "url_refilter_runs" in existing_tables:
        op.drop_table("url_refilter_runs")


def downgrade() -> None:
    """Recreate the URL refilter tracking tables for rollback compatibility."""
    existing_tables = _table_names()
    if "url_refilter_runs" not in existing_tables:
        op.create_table(
            "url_refilter_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("filter_chain_version", sa.Text(), nullable=False, server_default=""),
            sa.Column("crawler_was_running", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("backup_path", sa.Text(), nullable=True),
            sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("scanned_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("unchanged_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("activated_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("deactivated_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("retagged_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_raw_url_id", sa.Integer(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    if "url_refilter_run_events" not in existing_tables:
        op.create_table(
            "url_refilter_run_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "run_id",
                sa.Integer(),
                sa.ForeignKey("url_refilter_runs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_url_refilter_run_events_run_id", "url_refilter_run_events", ["run_id"])
