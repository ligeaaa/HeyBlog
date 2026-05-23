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
from trainer.pipelines.build_embeddings import run_build_embeddings
from trainer.pipelines.full_run import run_full_pipeline
from trainer.pipelines.prepare_dataset import run_prepare_dataset
from trainer.pipelines.qwen_embedding_run import run_qwen_embedding_pipeline
from trainer.pipelines.train_baseline import run_train_baseline
from trainer.graph.pipeline import run_train_gcn


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

    embeddings = subparsers.add_parser("build-embeddings", help="Generate reusable Qwen embeddings for a prepared dataset")
    embeddings.add_argument("--dataset-dir", type=Path, default=_latest_child(DEFAULT_DATASET_ROOT))
    embeddings.add_argument("--output-dir", type=Path, default=None)

    train = subparsers.add_parser("train", help="Train one baseline model")
    train.add_argument("--dataset-dir", type=Path, default=_latest_child(DEFAULT_DATASET_ROOT))
    train.add_argument("--model", choices=list(SUPPORTED_MODELS), default="structured")
    train.add_argument("--embedding-manifest", type=Path, default=None)

    evaluate = subparsers.add_parser("evaluate", help="Evaluate one trained run directory")
    evaluate.add_argument("--run-dir", type=Path, default=_latest_model_run(DEFAULT_MODEL_ROOT))

    full = subparsers.add_parser("full-run", help="Prepare dataset, train both baselines, and evaluate both")
    full.add_argument("--source-csv", type=Path, default=None)
    full.add_argument("--dataset-version", type=str, default=None)

    qwen = subparsers.add_parser("qwen-embedding-run", help="Prepare data, build Qwen embeddings, train, and evaluate")
    qwen.add_argument("--source-csv", type=Path, default=Path("data/blog-label-training-2026-04-11-with-text.csv"))
    qwen.add_argument("--dataset-version", type=str, default=None)
    qwen.add_argument("--run-id", type=str, default=None)

    gcn = subparsers.add_parser("train-gcn", help="Train and evaluate a simple graph GCN")
    gcn.add_argument("--dataset-dir", type=Path, default=Path("data/dataset"))
    gcn.add_argument("--output-dir", type=Path, default=None)
    gcn.add_argument("--max-features", type=int, default=4096)
    gcn.add_argument("--hidden-dim", type=int, default=64)
    gcn.add_argument("--epochs", type=int, default=200)
    gcn.add_argument("--learning-rate", type=float, default=0.01)
    gcn.add_argument("--weight-decay", type=float, default=5e-4)
    gcn.add_argument("--dropout", type=float, default=0.35)
    gcn.add_argument("--patience", type=int, default=25)
    gcn.add_argument("--seed", type=int, default=7)
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
    elif args.command == "build-embeddings":
        if args.dataset_dir is None:
            raise SystemExit(f"No dataset directory found under {DEFAULT_DATASET_ROOT}. Run prepare-dataset first.")
        payload = run_build_embeddings(dataset_dir=args.dataset_dir, output_dir=args.output_dir)
    elif args.command == "train":
        if args.dataset_dir is None:
            raise SystemExit(f"No dataset directory found under {DEFAULT_DATASET_ROOT}. Run prepare-dataset first.")
        payload = run_train_baseline(
            dataset_dir=args.dataset_dir,
            model_name=args.model,
            embedding_manifest=args.embedding_manifest,
        )
    elif args.command == "evaluate":
        if args.run_dir is None:
            raise SystemExit(f"No run directory found under {DEFAULT_MODEL_ROOT}. Run train or full-run first.")
        payload = run_evaluate_run(run_dir=args.run_dir)
    elif args.command == "train-gcn":
        payload = run_train_gcn(
            dataset_dir=args.dataset_dir,
            output_dir=args.output_dir,
            max_features=args.max_features,
            hidden_dim=args.hidden_dim,
            epochs=args.epochs,
            learning_rate=args.learning_rate,
            weight_decay=args.weight_decay,
            dropout=args.dropout,
            patience=args.patience,
            seed=args.seed,
        )
    elif args.command == "qwen-embedding-run":
        payload = run_qwen_embedding_pipeline(
            source_csv=args.source_csv,
            dataset_version=args.dataset_version,
            run_id=args.run_id,
        )
    else:
        payload = run_full_pipeline(source_csv=args.source_csv, dataset_version=args.dataset_version)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
