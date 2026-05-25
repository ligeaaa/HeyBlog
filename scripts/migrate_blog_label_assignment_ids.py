"""Compatibility wrapper for the retired multi-table label migration.

Label data now lives in the single ``blog_labels`` table keyed by
``normalized_url`` with ``label_id`` as a JSON count dictionary. Startup schema
sync and Alembic migrations perform the old assignment/tag/subject collapse, so
this script only triggers schema sync for older operational runbooks.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import inspect

from persistence_api.repository import build_repository
from persistence_api.repository import ensure_legacy_compat_schema
from shared.config import Settings


@dataclass(slots=True)
class MigrationSummary:
    """Summary for the retired label-assignment migration command."""

    total_rows: int = 0
    migrated_rows: int = 0
    skipped_missing_blog: int = 0
    deleted_missing_raw: int = 0
    deleted_duplicate_target: int = 0
    skipped_already_aligned: int = 0
    blog_labels_rows: int = 0


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the compatibility command."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Kept for compatibility; schema sync is always safe.")
    parser.add_argument("--local-sqlite", action="store_true", help="Ignore HEYBLOG_DB_DSN and use SQLite.")
    parser.add_argument("--db-path", type=Path, default=None, help="Override the SQLite database path.")
    parser.add_argument("--db-dsn", default=None, help="Override the database DSN.")
    return parser.parse_args()


def migrate_blog_label_assignment_ids(*, repository: object, apply: bool) -> MigrationSummary:
    """Run schema sync and report the current single-table label row count.

    Args:
        repository: Built repository exposing ``engine``.
        apply: Compatibility flag; retained so old callers do not break.

    Returns:
        Summary showing zero assignment rewrites and the current ``blog_labels``
        row count.
    """

    del apply
    engine = repository.engine  # type: ignore[attr-defined]
    ensure_legacy_compat_schema(engine)
    inspector = inspect(engine)
    if "blog_labels" not in set(inspector.get_table_names()):
        return MigrationSummary()
    with engine.connect() as connection:
        count = int(connection.exec_driver_sql("SELECT COUNT(*) FROM blog_labels").scalar() or 0)
    return MigrationSummary(blog_labels_rows=count)


def print_summary(summary: MigrationSummary, *, apply: bool) -> None:
    """Print a compact compatibility summary."""

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"mode={mode}")
    print("migration=retired_single_table_label_store")
    print(f"blog_labels_rows={summary.blog_labels_rows}")


def main() -> int:
    """Run the compatibility command."""

    args = parse_args()
    settings = Settings.from_env()
    db_path = args.db_path or settings.db_path
    db_dsn = args.db_dsn if args.db_dsn is not None else settings.db_dsn
    if args.local_sqlite or db_dsn == "":
        db_dsn = None
    repository = build_repository(db_path=db_path, db_dsn=db_dsn, settings=settings)
    summary = migrate_blog_label_assignment_ids(repository=repository, apply=args.apply)
    print_summary(summary, apply=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
