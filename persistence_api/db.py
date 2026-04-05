"""SQLAlchemy engine and session helpers for persistence."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker


def normalize_database_url(database_url: str) -> str:
    """Normalize PostgreSQL URLs to the installed SQLAlchemy driver.

    SQLAlchemy treats ``postgresql://`` as the legacy psycopg2 driver by
    default, while this project installs ``psycopg`` (v3). Accept the shorter
    DSN form from env/config and map it to the correct driver automatically.
    """
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def create_persistence_engine(database_url: str) -> Engine:
    """Create the shared persistence engine."""
    return create_engine(normalize_database_url(database_url), future=True, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a sessionmaker bound to the persistence engine."""
    return sessionmaker(bind=engine, autoflush=False, future=True)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Yield one managed session with commit/rollback handling."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
