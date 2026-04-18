"""Lightweight dataset label counter for trainer datasets.

Usage examples:

    python -m trainer.temp.dataset_overview --dataset-dir data/trainer/datasets/<version>
    python -m trainer.temp.dataset_overview --dataset-dir data/trainer/datasets/<version> --split train
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from trainer.io.dataset_reader import read_jsonl


def _resolve_dataset_file(dataset_dir: Path, split: str | None) -> Path:
    """Return the JSONL file to inspect for one dataset overview request."""
    if split:
        return dataset_dir / f"{split}.jsonl"
    return dataset_dir / "full_supervised.jsonl"


def _count_binary_labels(dataset_file: Path) -> dict[str, int]:
    """Count blog and non_blog labels from one staged trainer dataset file."""
    if not dataset_file.exists():
        raise SystemExit(f"Dataset file {dataset_file} does not exist.")

    counts: Counter[str] = Counter()
    for row in read_jsonl(dataset_file):
        label = str(row.get("binary_label", "")).strip()
        if label in {"blog", "non_blog"}:
            counts[label] += 1

    return {
        "blog": counts.get("blog", 0),
        "non_blog": counts.get("non_blog", 0),
        "total": counts.get("blog", 0) + counts.get("non_blog", 0),
    }


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the temporary dataset overview script."""
    parser = argparse.ArgumentParser(description="Count blog vs non_blog samples in a trainer dataset.")
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        required=True,
        help="Dataset directory containing full_supervised.jsonl or split JSONL files.",
    )
    parser.add_argument(
        "--split",
        choices=("train", "val", "test"),
        default=None,
        help="Optional split to inspect. Defaults to full_supervised.jsonl when omitted.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, count labels, and print a compact JSON summary."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    dataset_file = _resolve_dataset_file(args.dataset_dir, args.split)
    counts = _count_binary_labels(dataset_file)
    print(
        json.dumps(
            {
                "dataset_dir": str(args.dataset_dir),
                "dataset_file": str(dataset_file),
                "split": args.split or "full_supervised",
                "counts": counts,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
