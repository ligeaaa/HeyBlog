"""Import legacy blog-label CSV rows into the current HeyBlog label tables.

The legacy dataset is expected to contain ``url,title,label`` columns. This
script maps old labels to current tag names, finds matching current blogs by
URL, and writes blog label assignments through the repository layer.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.exc import OperationalError

from persistence_api.repository import build_repository
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
    """Counters collected while importing one legacy label CSV.

    Args:
        total_rows: Number of CSV data rows scanned.
        importable_rows: Number of rows that matched one current labelable raw URL.
        imported_rows: Number of rows written to the current label tables.
        skipped_missing_blog: Rows whose URL had no labelable current raw URL match.
        skipped_not_finished: Backward-compatible counter for legacy summaries;
            this script now uses raw URL eligibility instead of FINISHED status.
        skipped_bad_label: Rows whose legacy label is unsupported.
        skipped_existing: Rows skipped because the blog was already labeled and
            ``--replace-existing`` was not enabled.
        labels_seen: Raw label distribution from the legacy CSV.
        labels_importable: Current label distribution among importable rows.
    """

    total_rows: int = 0
    importable_rows: int = 0
    imported_rows: int = 0
    skipped_missing_blog: int = 0
    skipped_not_finished: int = 0
    skipped_bad_label: int = 0
    skipped_existing: int = 0
    labels_seen: Counter[str] | None = None
    labels_importable: Counter[str] | None = None

    def __post_init__(self) -> None:
        """Initialize mutable counters when they were not provided.

        Args:
            None.

        Returns:
            None.
        """

        if self.labels_seen is None:
            self.labels_seen = Counter()
        if self.labels_importable is None:
            self.labels_importable = Counter()


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the legacy label importer.

    Args:
        None.

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
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write labels. Without this flag the script runs as a dry-run.",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Replace labels on already-labeled blogs. Default skips already-labeled blogs.",
    )
    parser.add_argument(
        "--rebuild-parquet",
        action="store_true",
        help="Rebuild the blog-label parquet export after a successful --apply run.",
    )
    parser.add_argument(
        "--local-sqlite",
        action="store_true",
        help="Ignore HEYBLOG_DB_DSN and use the configured/local SQLite database path.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Override the SQLite database path.",
    )
    parser.add_argument(
        "--db-dsn",
        default=None,
        help="Override the database DSN. Use an empty string with --db-dsn '' to force SQLite.",
    )
    return parser.parse_args()


def create_default_tags(repository: Any) -> dict[str, dict[str, Any]]:
    """Ensure default label tags exist and return them by slug.

    Args:
        repository: Repository instance used to create or fetch tags.

    Returns:
        Mapping from tag slug to tag payload.
    """

    tag_names = sorted(set(DEFAULT_LABEL_MAP.values()))
    return {
        tag["slug"]: tag
        for tag in (repository.create_blog_label_tag(name=tag_name) for tag_name in tag_names)
    }


def load_existing_tags(repository: Any) -> dict[str, dict[str, Any]]:
    """Load current label tags without creating missing rows.

    Args:
        repository: Repository instance used to list label tags.

    Returns:
        Mapping from tag slug to tag payload.
    """

    return {tag["slug"]: tag for tag in repository.list_blog_label_tags()}


def labelable_blog_match(repository: Any, url: str) -> dict[str, Any] | None:
    """Resolve a legacy URL to the current labelable raw URL blog.

    Args:
        repository: Repository instance used for URL lookup.
        url: Legacy CSV URL value.

    Returns:
        Blog payload when the URL exists in the shared labelable raw URL pool;
        otherwise ``None``.
    """

    return repository.get_labelable_blog_by_url(url=url)


def current_label_slugs_for_blog(repository: Any, blog: dict[str, Any]) -> list[str]:
    """Load current label slugs for a matched blog using its URL as lookup text.

    Args:
        repository: Repository instance used for candidate lookup.
        blog: Blog payload returned by URL lookup.

    Returns:
        Current label slug list, or an empty list when the blog is unlabeled.
    """

    page = repository.list_blog_labeling_candidates(
        page=1,
        page_size=5,
        labeled=True,
        sort="recently_labeled",
        q=str(blog.get("url") or blog.get("normalized_url") or blog["id"]),
    )
    for item in page.get("items", []):
        if int(item["id"]) == int(blog["id"]):
            return list(item.get("label_slugs", []))
    return []


def import_legacy_labels(
    *,
    repository: Any,
    source_csv: Path,
    apply: bool,
    replace_existing: bool,
) -> ImportSummary:
    """Scan and optionally import legacy labels.

    Args:
        repository: Repository instance used for tag creation, lookup, and label writes.
        source_csv: Legacy CSV path.
        apply: Whether to write labels. ``False`` performs a dry-run.
        replace_existing: Whether existing label assignments should be replaced.

    Returns:
        Import summary counters.
    """

    tags_by_slug = create_default_tags(repository) if apply else load_existing_tags(repository)
    summary = ImportSummary()
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

            blog = labelable_blog_match(repository, row["url"])
            if blog is None:
                summary.skipped_missing_blog += 1
                continue

            blog_id = int(blog["id"])
            existing_slugs = current_label_slugs_for_blog(repository, blog)
            if existing_slugs and not replace_existing:
                summary.skipped_existing += 1
                continue

            summary.importable_rows += 1
            summary.labels_importable[target_label] += 1
            if apply:
                repository.replace_blog_link_labels(
                    blog_id=blog_id,
                    tag_ids=[int(tags_by_slug[target_label]["id"])],
                )
                summary.imported_rows += 1

    return summary


def print_summary(summary: ImportSummary, *, apply: bool) -> None:
    """Print a compact import summary.

    Args:
        summary: Import summary to print.
        apply: Whether this run actually wrote labels.

    Returns:
        None.
    """

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"mode={mode}")
    print(f"total_rows={summary.total_rows}")
    print(f"importable_rows={summary.importable_rows}")
    print(f"imported_rows={summary.imported_rows}")
    print(f"skipped_missing_blog={summary.skipped_missing_blog}")
    print(f"skipped_not_finished={summary.skipped_not_finished}")
    print(f"skipped_bad_label={summary.skipped_bad_label}")
    print(f"skipped_existing={summary.skipped_existing}")
    print(f"labels_seen={dict(summary.labels_seen or {})}")
    print(f"labels_importable={dict(summary.labels_importable or {})}")


def main() -> int:
    """Run the legacy label import command.

    Args:
        None.

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
        repository = build_repository(
            db_path=db_path,
            db_dsn=db_dsn,
            settings=settings,
        )
    except OperationalError as exc:
        print(
            "database_connection_failed: 当前数据库配置不可访问。"
            "如果 .env 使用 Docker 内部主机 persistence-db，请在容器内运行本脚本；"
            "如果要跑本地 SQLite，请传 --local-sqlite --db-path <path>。",
            file=sys.stderr,
        )
        print(str(exc), file=sys.stderr)
        return 2
    summary = import_legacy_labels(
        repository=repository,
        source_csv=args.source_csv,
        apply=args.apply,
        replace_existing=args.replace_existing,
    )
    print_summary(summary, apply=args.apply)
    if args.apply and args.rebuild_parquet:
        parquet_status = repository.rebuild_blog_label_training_parquet()
        print(f"parquet={parquet_status['message']}")
    elif args.rebuild_parquet:
        print("parquet=skipped because --apply was not provided")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
