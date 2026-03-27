"""Compatibility shim for persistence API schema helpers."""

from persistence_api.schema import POSTGRES_STATEMENTS
from persistence_api.schema import SQLITE_SCHEMA_SQL
from persistence_api.schema import init_postgres_db
from persistence_api.schema import init_sqlite_db

__all__ = [
    "POSTGRES_STATEMENTS",
    "SQLITE_SCHEMA_SQL",
    "init_postgres_db",
    "init_sqlite_db",
]
