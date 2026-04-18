"""Consensus evaluation pipeline across the latest trainer models.

Usage example:

    python -m trainer.temp.consensus_pipeline --dataset-dir data/trainer/datasets/<version>

The script discovers the most recent run directory for every model stored under
``data/model/<model_name>/<YYMMDDHHMM>``. It loads each model, runs inference on
the provided test dataset, and applies a strict consensus rule: a sample is
classified as ``non_blog`` only when every model predicts ``non_blog``.
Otherwise the consensus label is ``blog``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from trainer.constants import DEFAULT_MODEL_ROOT
from trainer.dataset.schema import SupervisedSample
from trainer.io.artifact_writer import write_csv
from trainer.io.dataset_reader import read_jsonl
from trainer.models.inference import load_model


def _latest_child(path: Path) -> Path | None:
    if not path.exists():
        return None
    children = sorted((child for child in path.iterdir() if child.is_dir()), key=lambda child: child.name)
    if not children:
        return None
    return children[-1]


def _discover_latest_runs(model_root: Path) -> dict[str, Path]:
    runs: dict[str, Path] = {}
    if not model_root.exists():
        raise SystemExit(f"Model root {model_root} does not exist. Train at least one model first.")
    for model_dir in sorted((child for child in model_root.iterdir() if child.is_dir()), key=lambda child: child.name):
        latest_run = _latest_child(model_dir)
        if latest_run is not None:
            runs[model_dir.name] = latest_run
    if not runs:
        raise SystemExit(f"No model runs found under {model_root}.")
    return runs


def _deserialize_samples(rows: list[dict[str, Any]]) -> list[SupervisedSample]:
    return [SupervisedSample(**row) for row in rows]


def _load_config(run_dir: Path) -> dict[str, Any]:
    return json.loads((run_dir / "config.json").read_text(encoding="utf-8"))


def _resolve_dataset_dir(explicit: Path | None, configs: dict[str, dict[str, Any]]) -> Path:
    if explicit is not None:
        return explicit
    dataset_dirs = {Path(config["dataset_dir"]) for config in configs.values()}
    if len(dataset_dirs) != 1:
        raise SystemExit(
            "Unable to infer dataset directory automatically because the latest runs "
            "reference multiple dataset paths. Pass --dataset-dir explicitly."
        )
    return dataset_dirs.pop()


def _load_test_samples(dataset_dir: Path) -> list[SupervisedSample]:
    test_path = dataset_dir / "test.jsonl"
    if not test_path.exists():
        raise SystemExit(f"Missing test split at {test_path}.")
    return _deserialize_samples(read_jsonl(test_path))


def _build_consensus_rows(
    samples: list[SupervisedSample],
    per_model_predictions: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    fieldnames = [
        "sample_id",
        "url",
        "title",
        "gold_label",
        "consensus_label",
        "blog_votes",
        "non_blog_votes",
        "per_model_predictions",
    ]
    rows: list[dict[str, Any]] = []
    metrics = {
        "total": len(samples),
        "consensus_blog": 0,
        "consensus_non_blog": 0,
        "tp": 0,
        "tn": 0,
        "fp": 0,
        "fn": 0,
    }
    for index, sample in enumerate(samples):
        per_model_labels: dict[str, tuple[str, float]] = {}
        for model_name in sorted(per_model_predictions):
            payload = per_model_predictions[model_name]
            probs = payload["probabilities"]
            threshold = payload["threshold"]
            prob_blog = probs[index]
            label = "blog" if prob_blog >= threshold else "non_blog"
            per_model_labels[model_name] = (label, prob_blog)
        blog_votes = sum(1 for label, _ in per_model_labels.values() if label == "blog")
        non_blog_votes = len(per_model_labels) - blog_votes
        consensus_label = "non_blog" if blog_votes == 0 else "blog"
        metrics["consensus_blog" if consensus_label == "blog" else "consensus_non_blog"] += 1
        gold = sample.binary_label
        if consensus_label == gold:
            if consensus_label == "blog":
                metrics["tp"] += 1
            else:
                metrics["tn"] += 1
        else:
            if consensus_label == "blog":
                metrics["fp"] += 1
            else:
                metrics["fn"] += 1
        rows.append(
            {
                "sample_id": sample.sample_id,
                "url": sample.url,
                "title": sample.title,
                "gold_label": gold,
                "consensus_label": consensus_label,
                "blog_votes": blog_votes,
                "non_blog_votes": non_blog_votes,
                "per_model_predictions": ";".join(
                    f"{model}:{label}:{prob:.4f}"
                    for model, (label, prob) in per_model_labels.items()
                ),
            }
        )
    metrics["accuracy"] = (
        (metrics["tp"] + metrics["tn"]) / metrics["total"] if metrics["total"] else 0.0
    )
    return rows, {"fieldnames": fieldnames, "metrics": metrics}


def _run_consensus(args: argparse.Namespace) -> dict[str, Any]:
    model_root: Path = args.model_root
    runs = _discover_latest_runs(model_root)
    configs = {model: _load_config(path) for model, path in runs.items()}
    dataset_dir = _resolve_dataset_dir(args.dataset_dir, configs)
    samples = _load_test_samples(dataset_dir)

    per_model_predictions: dict[str, dict[str, Any]] = {}
    for model_name, run_dir in runs.items():
        model = load_model(run_dir / "model.joblib")
        probabilities = model.predict_proba(samples)
        per_model_predictions[model_name] = {
            "threshold": getattr(model, "threshold", configs[model_name]["model_config"]["threshold"]),
            "probabilities": probabilities,
            "run_dir": str(run_dir),
        }

    rows, metadata = _build_consensus_rows(samples, per_model_predictions)
    output_path: Path = args.output
    write_csv(output_path, metadata["fieldnames"], rows)
    summary = {
        "dataset_dir": str(dataset_dir),
        "model_root": str(model_root),
        "runs": {model: str(path) for model, path in runs.items()},
        "output": str(output_path),
        "metrics": metadata["metrics"],
    }
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Consensus evaluator across latest trainer models.")
    parser.add_argument("--dataset-dir", type=Path, default=None, help="Dataset directory containing test.jsonl.")
    parser.add_argument(
        "--model-root",
        type=Path,
        default=DEFAULT_MODEL_ROOT,
        help=f"Root directory containing model subdirectories (default: {DEFAULT_MODEL_ROOT}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("trainer/temp/consensus_predictions.csv"),
        help="CSV file to write per-sample consensus predictions.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    summary = _run_consensus(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
