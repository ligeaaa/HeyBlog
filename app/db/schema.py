"""Define and initialize the SQLite schema for crawler data."""

from __future__ import annotations

import sqlite3


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS blogs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL,
  normalized_url TEXT NOT NULL UNIQUE,
  domain TEXT NOT NULL,
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


def init_db(connection: sqlite3.Connection) -> None:
    """Create database tables when they do not already exist."""
    connection.executescript(SCHEMA_SQL)
    connection.commit()
