"""Import legacy URL label CSV rows into the URL-keyed label-count table.

The legacy CSV is expected to contain ``url,title,label`` columns. Unlike the
older importer, this command writes directly to ``blog_labels`` by normalized
URL, so labels can be restored before or after a recrawl. The command is a
dry-run by default; pass ``--apply`` to write data and ``--clear-existing`` to
empty ``blog_labels`` before importing. Use ``--titles-only`` to quickly
backfill titles on existing ``blog_labels`` rows without changing label counts.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from crawler.crawling.normalization import normalize_url
from persistence_api.models import BlogLabelModel
from persistence_api.repository import build_repository
from persistence_api.repository import now_utc
from persistence_api.db import session_scope
from shared.config import Settings


DEFAULT_SOURCE_CSV = Path("data/dataset/blog-label-training-2026-04-11.csv")
DEFAULT_LABEL_MAP = {
    "blog": "blog",
    "company": "company",
    "other": "other",
    "others": "other",
    "unknown": "unknown",
}


@dataclass(slots=True)
class ImportSummary:
    """Counters collected while importing legacy URL labels.

    Args:
        total_rows: Number of CSV data rows scanned.
        importable_rows: Number of rows with supported labels and valid URLs.
        imported_urls: Number of URL label rows written.
        imported_label_counts: Number of label votes written across all URLs.
        updated_titles: Number of existing URL label rows whose title was updated.
        title_updates_available: Number of existing URL label rows that can
            receive a non-empty title from the CSV.
        cleared_existing: Number of existing ``blog_labels`` rows cleared.
        skipped_bad_label: Rows whose label is not supported by the map.
        skipped_bad_url: Rows whose URL could not be normalized.
        labels_seen: Raw label distribution in the CSV.
        labels_importable: Normalized label distribution that can be imported.
    """

    total_rows: int = 0
    importable_rows: int = 0
    imported_urls: int = 0
    imported_label_counts: int = 0
    updated_titles: int = 0
    title_updates_available: int = 0
    cleared_existing: int = 0
    skipped_bad_label: int = 0
    skipped_bad_url: int = 0
    labels_seen: Counter[str] | None = None
    labels_importable: Counter[str] | None = None

    def __post_init__(self) -> None:
        """Initialize mutable counters when absent."""
        if self.labels_seen is None:
            self.labels_seen = Counter()
        if self.labels_importable is None:
            self.labels_importable = Counter()


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the URL-keyed legacy importer.

    Returns:
        Parsed argparse namespace.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source_csv",
        nargs="?",
        type=Path,
        default=DEFAULT_SOURCE_CSV,
        help=f"Legacy CSV path. Defaults to {DEFAULT_SOURCE_CSV}.",
    )
    parser.add_argument("--apply", action="store_true", help="Write changes. Default is dry-run.")
    parser.add_argument(
        "--clear-existing",
        action="store_true",
        help="Delete all rows from blog_labels before importing. Requires --apply.",
    )
    parser.add_argument(
        "--titles-only",
        action="store_true",
        help=(
            "Only backfill title on existing blog_labels rows from the CSV. "
            "Does not create rows or change label counts."
        ),
    )
    parser.add_argument(
        "--rebuild-parquet",
        action="store_true",
        help="Rebuild the blog-label parquet export after a successful --apply run.",
    )
    parser.add_argument("--local-sqlite", action="store_true", help="Ignore HEYBLOG_DB_DSN and use SQLite.")
    parser.add_argument("--db-path", type=Path, default=None, help="Override the SQLite database path.")
    parser.add_argument("--db-dsn", default=None, help="Override the database DSN.")
    return parser.parse_args()


def _normalized_label_lookup(repository: Any) -> dict[str, int]:
    """Return known label IDs keyed by slug from ``blog_label_tags``.

    Args:
        repository: Repository instance exposing label tag helpers.

    Returns:
        Mapping from label slug to persisted label id.
    """

    for label_name in sorted(set(DEFAULT_LABEL_MAP.values())):
        repository.create_blog_label_tag(name=label_name)
    return {str(tag["slug"]): int(tag["id"]) for tag in repository.list_blog_label_tags()}


def _load_csv_counts(
    *,
    source_csv: Path,
    label_ids_by_slug: dict[str, int],
    summary: ImportSummary,
) -> tuple[dict[str, dict[str, int]], dict[str, str]]:
    """Load legacy CSV rows into URL-keyed label count dictionaries.

    Args:
        source_csv: CSV file containing ``url,title,label`` columns.
        label_ids_by_slug: Known label id mapping keyed by label slug.
        summary: Mutable summary counters to update.

    Returns:
        Tuple containing the normalized URL label-count mapping and a title
        mapping keyed by normalized URL.
    """

    counts_by_url: dict[str, dict[str, int]] = {}
    titles_by_url: dict[str, str] = {}
    with source_csv.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            summary.total_rows += 1
            raw_label = (row.get("label") or "").strip()
            summary.labels_seen[raw_label] += 1
            target_label = DEFAULT_LABEL_MAP.get(raw_label)
            if target_label is None:
                summary.skipped_bad_label += 1
                continue
            label_id = label_ids_by_slug.get(target_label)
            if label_id is None:
                summary.skipped_bad_label += 1
                continue
            try:
                normalized_view = normalize_url(str(row.get("url") or ""))
            except ValueError:
                summary.skipped_bad_url += 1
                continue
            if not normalized_view.domain:
                summary.skipped_bad_url += 1
                continue
            normalized = normalized_view.normalized_url
            url_counts = counts_by_url.setdefault(normalized, {})
            title = (row.get("title") or "").strip()
            if title and not titles_by_url.get(normalized):
                titles_by_url[normalized] = title
            label_key = str(label_id)
            url_counts[label_key] = int(url_counts.get(label_key, 0)) + 1
            summary.importable_rows += 1
            summary.labels_importable[target_label] += 1
    return counts_by_url, titles_by_url


def import_legacy_label_counts(
    *,
    repository: Any,
    source_csv: Path,
    apply: bool,
    clear_existing: bool,
    titles_only: bool = False,
) -> ImportSummary:
    """Scan and optionally import legacy URL label counts.

    Args:
        repository: Repository instance exposing a SQLAlchemy session factory.
        source_csv: CSV file containing legacy labels.
        apply: Whether to write changes. ``False`` performs a dry-run.
        clear_existing: Whether to clear ``blog_labels`` before importing.
        titles_only: Whether to update only existing ``blog_labels.title``
            values from the CSV.

    Returns:
        Import summary counters.
    """

    if clear_existing and not apply:
        raise ValueError("--clear-existing requires --apply")
    if titles_only and clear_existing:
        raise ValueError("--titles-only cannot be combined with --clear-existing")
    summary = ImportSummary()
    label_ids_by_slug = _normalized_label_lookup(repository)
    counts_by_url, titles_by_url = _load_csv_counts(
        source_csv=source_csv,
        label_ids_by_slug=label_ids_by_slug,
        summary=summary,
    )
    if titles_only:
        with session_scope(repository.session_factory) as session:
            existing_rows = session.scalars(
                select(BlogLabelModel).where(BlogLabelModel.normalized_url.in_(list(titles_by_url)))
            ).all()
            rows_to_update = [
                row
                for row in existing_rows
                if titles_by_url.get(row.normalized_url)
                and (row.title or "").strip() != titles_by_url[row.normalized_url]
            ]
            summary.title_updates_available = len(rows_to_update)
            if apply:
                timestamp = now_utc()
                for row in rows_to_update:
                    row.title = titles_by_url[row.normalized_url]
                    row.updated_time = timestamp
                summary.updated_titles = len(rows_to_update)
        return summary

    if not apply:
        summary.imported_urls = len(counts_by_url)
        summary.imported_label_counts = sum(sum(label_counts.values()) for label_counts in counts_by_url.values())
        return summary

    timestamp = now_utc()
    with session_scope(repository.session_factory) as session:
        if clear_existing:
            summary.cleared_existing = len(session.scalars(select(BlogLabelModel)).all())
            session.execute(delete(BlogLabelModel))
        for normalized_url, label_counts in sorted(counts_by_url.items()):
            row = session.get(BlogLabelModel, normalized_url)
            if row is None:
                row = BlogLabelModel(
                    normalized_url=normalized_url,
                    title=titles_by_url.get(normalized_url, ""),
                    label_id=dict(label_counts),
                    created_time=timestamp,
                    updated_time=timestamp,
                )
                session.add(row)
            else:
                existing = dict(row.label_id or {})
                for label_id, count in label_counts.items():
                    existing[str(label_id)] = int(existing.get(str(label_id), 0)) + int(count)
                if titles_by_url.get(normalized_url):
                    row.title = titles_by_url[normalized_url]
                row.label_id = existing
                row.updated_time = timestamp
        summary.imported_urls = len(counts_by_url)
        summary.imported_label_counts = sum(sum(label_counts.values()) for label_counts in counts_by_url.values())
    return summary


def print_summary(summary: ImportSummary, *, apply: bool) -> None:
    """Print a compact import summary.

    Args:
        summary: Summary counters to print.
        apply: Whether the run wrote data.

    Returns:
        None.
    """

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"mode={mode}")
    print(f"total_rows={summary.total_rows}")
    print(f"importable_rows={summary.importable_rows}")
    print(f"imported_urls={summary.imported_urls}")
    print(f"imported_label_counts={summary.imported_label_counts}")
    print(f"title_updates_available={summary.title_updates_available}")
    print(f"updated_titles={summary.updated_titles}")
    print(f"cleared_existing={summary.cleared_existing}")
    print(f"skipped_bad_label={summary.skipped_bad_label}")
    print(f"skipped_bad_url={summary.skipped_bad_url}")
    print(f"labels_seen={dict(summary.labels_seen or {})}")
    print(f"labels_importable={dict(summary.labels_importable or {})}")


def main() -> int:
    """Run the legacy URL label-count import command.

    Returns:
        Process exit code.
    """

    args = parse_args()
    settings = Settings.from_env()
    db_path = args.db_path or settings.db_path
    db_dsn = args.db_dsn if args.db_dsn is not None else settings.db_dsn
    if args.local_sqlite or db_dsn == "":
        db_dsn = None
    try:
        repository = build_repository(db_path=db_path, db_dsn=db_dsn, settings=settings)
    except OperationalError as exc:
        print(
            "database_connection_failed: 当前数据库配置不可访问。"
            "如果 .env 使用 Docker 内部主机 persistence-db，请在容器内运行本脚本；"
            "如果要跑本地 SQLite，请传 --local-sqlite --db-path <path>。",
            file=sys.stderr,
        )
        print(str(exc), file=sys.stderr)
        return 2
    try:
        summary = import_legacy_label_counts(
            repository=repository,
            source_csv=args.source_csv,
            apply=args.apply,
            clear_existing=args.clear_existing,
            titles_only=args.titles_only,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print_summary(summary, apply=args.apply)
    if args.apply and args.rebuild_parquet:
        parquet_status = repository.rebuild_blog_label_training_parquet()
        print(f"parquet={parquet_status['message']}")
    elif args.rebuild_parquet:
        print("parquet=skipped because --apply was not provided")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
