"""Regression tests for repository import and backend selection."""

from pathlib import Path

import pytest

import persistence_api.repository as repository_module


def test_build_repository_uses_sqlite_when_psycopg_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SQLite repository creation should not require the PostgreSQL driver."""
    monkeypatch.setattr(repository_module, "psycopg", None)
    monkeypatch.setattr(repository_module, "dict_row", None)

    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    blog_id, inserted = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
        depth=0,
        source_blog_id=None,
    )

    assert inserted is True
    assert repository.get_blog(blog_id)["domain"] == "blog.example.com"


def test_build_repository_raises_helpful_error_for_postgres_without_psycopg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Postgres path should fail with an actionable error when psycopg is absent."""
    monkeypatch.setattr(repository_module, "psycopg", None)
    monkeypatch.setattr(repository_module, "dict_row", None)

    with pytest.raises(ModuleNotFoundError, match="psycopg"):
        repository_module.build_repository(
            db_path=tmp_path / "db.sqlite",
            db_dsn="postgresql://heyblog:heyblog@persistence-db:5432/heyblog",
        )
