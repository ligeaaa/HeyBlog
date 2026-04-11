"""CLI for the offline trainer workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from trainer.pipelines.evaluate_run import run_evaluate_run
from trainer.pipelines.full_run import run_full_pipeline
from trainer.pipelines.prepare_dataset import run_prepare_dataset
from trainer.pipelines.train_baseline import run_train_baseline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline training workflow for blog URL classification")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare-dataset", help="Build dataset artifacts from the raw label export")
    prepare.add_argument("--source-csv", type=Path, default=None)
    prepare.add_argument("--dataset-version", type=str, default=None)

    train = subparsers.add_parser("train", help="Train one baseline model")
    train.add_argument("--dataset-dir", type=Path, required=True)
    train.add_argument("--model", choices=["structured", "tfidf"], required=True)

    evaluate = subparsers.add_parser("evaluate", help="Evaluate one trained run directory")
    evaluate.add_argument("--run-dir", type=Path, required=True)

    full = subparsers.add_parser("full-run", help="Prepare dataset, train both baselines, and evaluate both")
    full.add_argument("--source-csv", type=Path, default=None)
    full.add_argument("--dataset-version", type=str, default=None)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "prepare-dataset":
        payload = run_prepare_dataset(source_csv=args.source_csv, dataset_version=args.dataset_version)
    elif args.command == "train":
        payload = run_train_baseline(dataset_dir=args.dataset_dir, model_name=args.model)
    elif args.command == "evaluate":
        payload = run_evaluate_run(run_dir=args.run_dir)
    else:
        payload = run_full_pipeline(source_csv=args.source_csv, dataset_version=args.dataset_version)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
