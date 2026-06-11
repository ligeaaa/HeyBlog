"""Add local recommendation request, impression, and interaction tables.

Revision ID: 20260607_01
Revises: 20260606_01
Create Date: 2026-06-07 14:21:29 BST
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260607_01"
down_revision = "20260606_01"
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
    """Create the recommendation event substrate tables.

    Args:
        None.

    Returns:
        None. The migration mutates the active database schema in place.
    """

    tables = _tables()
    if "recommendation_requests" not in tables:
        op.create_table(
            "recommendation_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("request_uuid", sa.Text(), nullable=False),
            sa.Column("surface", sa.Text(), nullable=False),
            sa.Column("strategy", sa.Text(), nullable=False),
            sa.Column("strategy_version", sa.Text(), nullable=False, server_default="v1"),
            sa.Column("visitor_id", sa.Text(), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("session_id", sa.Text(), nullable=False),
            sa.Column("source", sa.Text(), nullable=True),
            sa.Column("page_url", sa.Text(), nullable=True),
            sa.Column("requested_count", sa.Integer(), nullable=False),
            sa.Column("served_count", sa.Integer(), nullable=False),
            sa.Column("context_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("request_uuid", name="uq_recommendation_requests_request_uuid"),
        )
        op.create_index("ix_recommendation_requests_request_uuid", "recommendation_requests", ["request_uuid"])
        op.create_index("ix_recommendation_requests_surface", "recommendation_requests", ["surface"])
        op.create_index("ix_recommendation_requests_user_id", "recommendation_requests", ["user_id"])
        op.create_index("ix_recommendation_requests_visitor_id", "recommendation_requests", ["visitor_id"])
        op.create_index("ix_recommendation_requests_session_id", "recommendation_requests", ["session_id"])
        op.create_index(
            "ix_recommendation_requests_surface_created",
            "recommendation_requests",
            ["surface", "created_at"],
        )
        op.create_index(
            "ix_recommendation_requests_strategy_created",
            "recommendation_requests",
            ["strategy", "strategy_version", "created_at"],
        )

    tables = _tables()
    if "recommendation_impressions" not in tables:
        op.create_table(
            "recommendation_impressions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "request_id",
                sa.Integer(),
                sa.ForeignKey("recommendation_requests.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("normalized_url", sa.Text(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("score", sa.Integer(), nullable=True),
            sa.Column("reason_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("request_id", "position", name="uq_recommendation_impression_request_position"),
            sa.UniqueConstraint("request_id", "normalized_url", name="uq_recommendation_impression_request_url"),
        )
        op.create_index("ix_recommendation_impressions_request_id", "recommendation_impressions", ["request_id"])
        op.create_index("ix_recommendation_impressions_normalized_url", "recommendation_impressions", ["normalized_url"])
        op.create_index(
            "ix_recommendation_impressions_url_created",
            "recommendation_impressions",
            ["normalized_url", "created_at"],
        )

    tables = _tables()
    if "blog_interactions" not in tables:
        op.create_table(
            "blog_interactions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_uuid", sa.Text(), nullable=False),
            sa.Column(
                "request_id",
                sa.Integer(),
                sa.ForeignKey("recommendation_requests.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "impression_id",
                sa.Integer(),
                sa.ForeignKey("recommendation_impressions.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("normalized_url", sa.Text(), nullable=False),
            sa.Column("event_type", sa.Text(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=True),
            sa.Column("entrance_kind", sa.Text(), nullable=False),
            sa.Column("entrance_url", sa.Text(), nullable=False),
            sa.Column("interaction_order", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("visitor_id", sa.Text(), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("session_id", sa.Text(), nullable=False),
            sa.Column("client_event_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("attributes_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("event_uuid", name="uq_blog_interactions_event_uuid"),
        )
        op.create_index("ix_blog_interactions_event_uuid", "blog_interactions", ["event_uuid"])
        op.create_index("ix_blog_interactions_request_id", "blog_interactions", ["request_id"])
        op.create_index("ix_blog_interactions_impression_id", "blog_interactions", ["impression_id"])
        op.create_index("ix_blog_interactions_normalized_url", "blog_interactions", ["normalized_url"])
        op.create_index("ix_blog_interactions_event_type", "blog_interactions", ["event_type"])
        op.create_index("ix_blog_interactions_entrance_kind", "blog_interactions", ["entrance_kind"])
        op.create_index("ix_blog_interactions_entrance_url", "blog_interactions", ["entrance_url"])
        op.create_index("ix_blog_interactions_visitor_id", "blog_interactions", ["visitor_id"])
        op.create_index("ix_blog_interactions_user_id", "blog_interactions", ["user_id"])
        op.create_index("ix_blog_interactions_session_id", "blog_interactions", ["session_id"])
        op.create_index(
            "ix_blog_interactions_url_event_created",
            "blog_interactions",
            ["normalized_url", "event_type", "created_at"],
        )
        op.create_index("ix_blog_interactions_request_event", "blog_interactions", ["request_id", "event_type"])


def downgrade() -> None:
    """Drop the recommendation event substrate tables.

    Args:
        None.

    Returns:
        None. The migration mutates the active database schema in place.
    """

    tables = _tables()
    if "blog_interactions" in tables:
        op.drop_table("blog_interactions")
    tables = _tables()
    if "recommendation_impressions" in tables:
        op.drop_table("recommendation_impressions")
    tables = _tables()
    if "recommendation_requests" in tables:
        op.drop_table("recommendation_requests")
