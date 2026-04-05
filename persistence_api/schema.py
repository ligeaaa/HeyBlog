"""Deprecated schema bootstrap helpers.

The persistence layer now owns table creation through SQLAlchemy metadata and
will be migrated to Alembic-managed DDL. These no-op functions remain only as
compatibility shims for older imports.
"""

from __future__ import annotations

from typing import Any


def init_sqlite_db(connection: Any) -> None:
    """No-op compatibility shim."""
    _ = connection


def init_postgres_db(connection: Any) -> None:
    """No-op compatibility shim."""
    _ = connection
