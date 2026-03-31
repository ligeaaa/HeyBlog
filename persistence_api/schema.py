"""Define and initialize the SQLite and PostgreSQL schemas for crawler data."""

from __future__ import annotations

import sqlite3
from typing import Any


SQLITE_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS blogs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL,
  normalized_url TEXT NOT NULL UNIQUE,
  domain TEXT NOT NULL,
  title TEXT,
  icon_url TEXT,
  status_code INTEGER,
  crawl_status TEXT NOT NULL DEFAULT 'WAITING',
  friend_links_count INTEGER NOT NULL DEFAULT 0,
  depth INTEGER NOT NULL DEFAULT 0,
  source_blog_id INTEGER,
  last_crawled_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(source_blog_id) REFERENCES blogs(id)
);

CREATE TABLE IF NOT EXISTS edges (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  from_blog_id INTEGER NOT NULL,
  to_blog_id INTEGER NOT NULL,
  link_url_raw TEXT NOT NULL,
  link_text TEXT,
  discovered_at TEXT NOT NULL,
  UNIQUE(from_blog_id, to_blog_id),
  FOREIGN KEY(from_blog_id) REFERENCES blogs(id) ON DELETE CASCADE,
  FOREIGN KEY(to_blog_id) REFERENCES blogs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS crawl_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  blog_id INTEGER,
  stage TEXT NOT NULL,
  result TEXT NOT NULL,
  message TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(blog_id) REFERENCES blogs(id) ON DELETE SET NULL
);
"""


POSTGRES_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS blogs (
      id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      url TEXT NOT NULL,
      normalized_url TEXT NOT NULL UNIQUE,
      domain TEXT NOT NULL,
      title TEXT,
      icon_url TEXT,
      status_code INTEGER,
      crawl_status TEXT NOT NULL DEFAULT 'WAITING',
      friend_links_count INTEGER NOT NULL DEFAULT 0,
      depth INTEGER NOT NULL DEFAULT 0,
      source_blog_id BIGINT,
      last_crawled_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL,
      updated_at TIMESTAMPTZ NOT NULL,
      FOREIGN KEY(source_blog_id) REFERENCES blogs(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS edges (
      id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      from_blog_id BIGINT NOT NULL,
      to_blog_id BIGINT NOT NULL,
      link_url_raw TEXT NOT NULL,
      link_text TEXT,
      discovered_at TIMESTAMPTZ NOT NULL,
      UNIQUE(from_blog_id, to_blog_id),
      FOREIGN KEY(from_blog_id) REFERENCES blogs(id) ON DELETE CASCADE,
      FOREIGN KEY(to_blog_id) REFERENCES blogs(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS crawl_logs (
      id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      blog_id BIGINT,
      stage TEXT NOT NULL,
      result TEXT NOT NULL,
      message TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL,
      FOREIGN KEY(blog_id) REFERENCES blogs(id) ON DELETE SET NULL
    )
    """,
)


def _sqlite_blog_columns(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(blogs)").fetchall()
    }


def _ensure_sqlite_blog_columns(connection: sqlite3.Connection) -> None:
    columns = _sqlite_blog_columns(connection)
    if "title" not in columns:
        connection.execute("ALTER TABLE blogs ADD COLUMN title TEXT")
    if "icon_url" not in columns:
        connection.execute("ALTER TABLE blogs ADD COLUMN icon_url TEXT")


def init_sqlite_db(connection: sqlite3.Connection) -> None:
    """Create database tables when they do not already exist."""
    connection.executescript(SQLITE_SCHEMA_SQL)
    _ensure_sqlite_blog_columns(connection)
    connection.commit()


def init_postgres_db(connection: Any) -> None:
    """Create PostgreSQL tables when they do not already exist."""
    with connection.cursor() as cursor:
        for statement in POSTGRES_STATEMENTS:
            cursor.execute(statement)
        cursor.execute("ALTER TABLE blogs ADD COLUMN IF NOT EXISTS title TEXT")
        cursor.execute("ALTER TABLE blogs ADD COLUMN IF NOT EXISTS icon_url TEXT")
