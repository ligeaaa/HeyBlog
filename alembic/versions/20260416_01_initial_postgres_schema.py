"""Initialize PostgreSQL persistence schema and Apache AGE extension."""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

from persistence_api.models import Base
from persistence_api.repository import ensure_legacy_compat_schema


revision = "20260416_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(text("CREATE EXTENSION IF NOT EXISTS age"))
    Base.metadata.create_all(bind=bind)
    ensure_legacy_compat_schema(bind.engine)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
