"""Drop deprecated ingestion request and blog dedup scan tables.

Revision ID: 20260607_03
Revises: 20260607_02
Create Date: 2026-06-07 16:30:00 BST
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260607_03"
down_revision = "20260607_02"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    """Return the current database table names.

    Args:
        None.

    Returns:
        Set of table names visible to the active migration connection.
    """

    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    """Remove persistence tables for deprecated ingestion and dedup scan features.

    Args:
        None.

    Returns:
        None. Existing deprecated tables are dropped when present.
    """

    tables = _table_names()
    for table_name in (
        "blog_dedup_scan_run_items",
        "blog_dedup_scan_runs",
        "ingestion_requests",
    ):
        if table_name in tables:
            op.drop_table(table_name)


def downgrade() -> None:
    """Recreate the deprecated tables with their final historical schema.

    Args:
        None.

    Returns:
        None. The removed tables are recreated for migration rollback only.
    """

    tables = _table_names()
    if "ingestion_requests" not in tables:
        op.create_table(
            "ingestion_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("requested_url", sa.Text(), nullable=False),
            sa.Column("normalized_url", sa.Text(), nullable=False),
            sa.Column("identity_key", sa.Text(), nullable=True),
            sa.Column("identity_reason_codes", sa.Text(), nullable=True),
            sa.Column("identity_ruleset_version", sa.Text(), nullable=True),
            sa.Column("requester_email", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("seed_blog_id", sa.Integer(), nullable=True),
            sa.Column("matched_blog_id", sa.Integer(), nullable=True),
            sa.Column("request_token", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["seed_blog_id"], ["blogs.blog_id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["matched_blog_id"], ["blogs.blog_id"], ondelete="SET NULL"),
        )
        op.create_index("ix_ingestion_requests_identity_key", "ingestion_requests", ["identity_key"])
        op.create_index("ix_ingestion_requests_status", "ingestion_requests", ["status"])
        op.create_index("ix_ingestion_requests_seed_blog_id", "ingestion_requests", ["seed_blog_id"])
        op.create_index("ix_ingestion_requests_matched_blog_id", "ingestion_requests", ["matched_blog_id"])

    if "blog_dedup_scan_runs" not in tables:
        op.create_table(
            "blog_dedup_scan_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("ruleset_version", sa.Text(), nullable=False),
            sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("scanned_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("removed_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("kept_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("crawler_was_running", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("crawler_restart_attempted", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("crawler_restart_succeeded", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("search_reindexed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
        )
        op.create_index("ix_blog_dedup_scan_runs_status", "blog_dedup_scan_runs", ["status"])

    if "blog_dedup_scan_run_items" not in tables:
        op.create_table(
            "blog_dedup_scan_run_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_id", sa.Integer(), nullable=False),
            sa.Column("survivor_blog_id", sa.Integer(), nullable=True),
            sa.Column("removed_blog_id", sa.Integer(), nullable=True),
            sa.Column("survivor_identity_key", sa.Text(), nullable=True),
            sa.Column("removed_identity_key", sa.Text(), nullable=True),
            sa.Column("removed_url", sa.Text(), nullable=False),
            sa.Column("reason_code", sa.Text(), nullable=False),
            sa.Column("reason_codes", sa.Text(), nullable=True),
            sa.Column("survivor_selection_basis", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["run_id"], ["blog_dedup_scan_runs.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["survivor_blog_id"], ["blogs.blog_id"], ondelete="SET NULL"),
        )
        op.create_index("ix_blog_dedup_scan_run_items_run_id", "blog_dedup_scan_run_items", ["run_id"])
