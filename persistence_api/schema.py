"""Define and initialize the SQLite and PostgreSQL schemas for crawler data."""

from __future__ import annotations

import sqlite3
from typing import Any


SQLITE_SCHEMA_TABLES_SQL = """
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

SQLITE_SCHEMA_SQL = f"""
PRAGMA foreign_keys = ON;

{SQLITE_SCHEMA_TABLES_SQL}
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


def _sqlite_column_expr(columns: set[str], column: str) -> str:
    return column if column in columns else f"NULL AS {column}"


def _ensure_sqlite_blog_columns(connection: sqlite3.Connection) -> None:
    columns = _sqlite_blog_columns(connection)
    if "title" not in columns:
        connection.execute("ALTER TABLE blogs ADD COLUMN title TEXT")
    if "icon_url" not in columns:
        connection.execute("ALTER TABLE blogs ADD COLUMN icon_url TEXT")


def _rebuild_sqlite_blogs_without_depth(connection: sqlite3.Connection) -> None:
    columns = _sqlite_blog_columns(connection)
    if "depth" not in columns:
        return

    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    blog_select = ", ".join(
        [
            "id",
            "url",
            "normalized_url",
            "domain",
            _sqlite_column_expr(columns, "title"),
            _sqlite_column_expr(columns, "icon_url"),
            _sqlite_column_expr(columns, "status_code"),
            "crawl_status",
            "friend_links_count",
            _sqlite_column_expr(columns, "source_blog_id"),
            _sqlite_column_expr(columns, "last_crawled_at"),
            "created_at",
            "updated_at",
        ]
    )
    connection.executescript(
        """
        ALTER TABLE edges RENAME TO edges_legacy_depth;
        ALTER TABLE crawl_logs RENAME TO crawl_logs_legacy_depth;
        ALTER TABLE blogs RENAME TO blogs_legacy_depth;
        """
    )
    connection.executescript(SQLITE_SCHEMA_TABLES_SQL)
    connection.execute(
        f"""
        INSERT INTO blogs (
          id, url, normalized_url, domain, title, icon_url, status_code, crawl_status,
          friend_links_count, source_blog_id, last_crawled_at, created_at, updated_at
        )
        SELECT {blog_select}
        FROM blogs_legacy_depth
        """
    )
    connection.execute(
        """
        INSERT INTO edges (
          id, from_blog_id, to_blog_id, link_url_raw, link_text, discovered_at
        )
        SELECT id, from_blog_id, to_blog_id, link_url_raw, link_text, discovered_at
        FROM edges_legacy_depth
        """
    )
    connection.execute(
        """
        INSERT INTO crawl_logs (
          id, blog_id, stage, result, message, created_at
        )
        SELECT id, blog_id, stage, result, message, created_at
        FROM crawl_logs_legacy_depth
        """
    )
    connection.executescript(
        """
        DROP TABLE edges_legacy_depth;
        DROP TABLE crawl_logs_legacy_depth;
        DROP TABLE blogs_legacy_depth;
        """
    )
    current_max_id = connection.execute("SELECT COALESCE(MAX(id), 0) FROM blogs").fetchone()
    connection.execute("DELETE FROM sqlite_sequence WHERE name IN ('blogs', 'blogs_legacy_depth')")
    connection.execute(
        "INSERT INTO sqlite_sequence(name, seq) VALUES ('blogs', ?)",
        (int(current_max_id[0]),),
    )
    connection.execute("PRAGMA foreign_keys = ON")
    connection.commit()


def init_sqlite_db(connection: sqlite3.Connection) -> None:
    """Create database tables when they do not already exist."""
    connection.executescript(SQLITE_SCHEMA_SQL)
    _rebuild_sqlite_blogs_without_depth(connection)
    _ensure_sqlite_blog_columns(connection)
    connection.commit()


def init_postgres_db(connection: Any) -> None:
    """Create PostgreSQL tables when they do not already exist."""
    with connection.cursor() as cursor:
        for statement in POSTGRES_STATEMENTS:
            cursor.execute(statement)
        cursor.execute("ALTER TABLE blogs ADD COLUMN IF NOT EXISTS title TEXT")
        cursor.execute("ALTER TABLE blogs ADD COLUMN IF NOT EXISTS icon_url TEXT")
