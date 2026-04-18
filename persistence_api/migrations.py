"""Programmatic migration entrypoint for PostgreSQL persistence startup."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_postgres_migrations(database_url: str) -> None:
    """Upgrade the PostgreSQL persistence schema to the latest Alembic revision."""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
