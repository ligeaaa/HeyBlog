"""CLI for the offline trainer workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from collections.abc import Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trainer.constants import DEFAULT_DATASET_ROOT
from trainer.constants import DEFAULT_MODEL_ROOT
from trainer.constants import SUPPORTED_MODELS
from trainer.pipelines.evaluate_run import run_evaluate_run
from trainer.pipelines.full_run import run_full_pipeline
from trainer.pipelines.prepare_dataset import run_prepare_dataset
from trainer.pipelines.train_baseline import run_train_baseline


def _latest_child(path: Path) -> Path | None:
    if not path.exists():
        return None
    children = sorted((child for child in path.iterdir() if child.is_dir()), key=lambda child: child.name)
    if not children:
        return None
    return children[-1]


def _latest_model_run(model_root: Path) -> Path | None:
    """Return the latest run directory across all model subdirectories."""
    if not model_root.exists():
        return None
    latest_path: Path | None = None
    latest_id: str | None = None
    for model_dir in sorted((child for child in model_root.iterdir() if child.is_dir()), key=lambda child: child.name):
        candidate = _latest_child(model_dir)
        if candidate is None:
            continue
        if latest_id is None or candidate.name > latest_id:
            latest_id = candidate.name
            latest_path = candidate
    return latest_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline training workflow for blog URL classification")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare-dataset", help="Build dataset artifacts from the raw label export")
    prepare.add_argument("--source-csv", type=Path, default=None)
    prepare.add_argument("--dataset-version", type=str, default=None)

    train = subparsers.add_parser("train", help="Train one baseline model")
    train.add_argument("--dataset-dir", type=Path, default=_latest_child(DEFAULT_DATASET_ROOT))
    train.add_argument("--model", choices=list(SUPPORTED_MODELS), default="structured")

    evaluate = subparsers.add_parser("evaluate", help="Evaluate one trained run directory")
    evaluate.add_argument("--run-dir", type=Path, default=_latest_model_run(DEFAULT_MODEL_ROOT))

    full = subparsers.add_parser("full-run", help="Prepare dataset, train both baselines, and evaluate both")
    full.add_argument("--source-csv", type=Path, default=None)
    full.add_argument("--dataset-version", type=str, default=None)
    return parser


def _resolve_argv(argv: Sequence[str] | None) -> list[str]:
    resolved = list(sys.argv[1:] if argv is None else argv)
    if resolved:
        return resolved
    return ["full-run"]


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(_resolve_argv(argv))
    if args.command == "prepare-dataset":
        payload = run_prepare_dataset(source_csv=args.source_csv, dataset_version=args.dataset_version)
    elif args.command == "train":
        if args.dataset_dir is None:
            raise SystemExit(f"No dataset directory found under {DEFAULT_DATASET_ROOT}. Run prepare-dataset first.")
        payload = run_train_baseline(dataset_dir=args.dataset_dir, model_name=args.model)
    elif args.command == "evaluate":
        if args.run_dir is None:
            raise SystemExit(f"No run directory found under {DEFAULT_MODEL_ROOT}. Run train or full-run first.")
        payload = run_evaluate_run(run_dir=args.run_dir)
    else:
        payload = run_full_pipeline(source_csv=args.source_csv, dataset_version=args.dataset_version)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
