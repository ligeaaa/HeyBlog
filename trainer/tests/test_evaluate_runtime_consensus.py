"""Tests for runtime consensus strategy evaluation."""

from __future__ import annotations

import json
from pathlib import Path

from trainer.io.artifact_writer import write_jsonl
from trainer.io.artifact_writer import write_pickle
from trainer.pipelines.evaluate_runtime_consensus import run_evaluate_runtime_consensus


class StubRuntimeModel:
    """Return deterministic probabilities for runtime consensus tests.

    Attributes:
        probabilities: Fixed blog probabilities returned in order.
        threshold: Per-model threshold used by vote strategies.
    """

    def __init__(self, probabilities: list[float], *, threshold: float = 0.5) -> None:
        """Store fixed probabilities and threshold.

        Args:
            probabilities: Blog probabilities returned for the requested test
                samples.
            threshold: Blog classification threshold exposed by the model.

        Returns:
            ``None``. The model only stores deterministic test values.
        """
        self.probabilities = probabilities
        self.threshold = threshold

    def predict_proba(self, samples: list[object]) -> list[float]:
        """Return the fixed probabilities for a matching sample batch.

        Args:
            samples: Input samples; only the batch size is validated.

        Returns:
            Blog probabilities configured for this stub.
        """
        if len(samples) != len(self.probabilities):
            raise ValueError("sample_count_mismatch")
        return self.probabilities


def _write_dataset(dataset_dir: Path) -> None:
    """Write a tiny prepared trainer test split.

    Args:
        dataset_dir: Destination dataset directory.

    Returns:
        ``None``. The function writes ``test.jsonl`` in place.
    """
    rows = [
        {
            "sample_id": "blog-1",
            "url": "https://blog.example/",
            "normalized_url": "https://blog.example/",
            "domain": "blog.example",
            "title": "Personal Blog",
            "raw_labels": ["blog"],
            "binary_label": "blog",
            "resolution_status": "supervised",
            "resolution_reason": "test",
            "title_missing": False,
            "split": "test",
            "text": "rss archive tags",
        },
        {
            "sample_id": "company-1",
            "url": "https://company.example/",
            "normalized_url": "https://company.example/",
            "domain": "company.example",
            "title": "Product Pricing",
            "raw_labels": ["company"],
            "binary_label": "non_blog",
            "resolution_status": "supervised",
            "resolution_reason": "test",
            "title_missing": False,
            "split": "test",
            "text": "pricing careers product",
        },
    ]
    write_jsonl(dataset_dir / "test.jsonl", rows)
    write_jsonl(dataset_dir / "val.jsonl", rows)


def _write_runtime_model(
    model_root: Path,
    model_name: str,
    probabilities: list[float],
    *,
    f1: float | None = None,
) -> None:
    """Write one pickled runtime model run.

    Args:
        model_root: Runtime model root directory.
        model_name: Model family name.
        probabilities: Fixed probabilities returned by the model.
        f1: Optional metric written as model weight.

    Returns:
        ``None``. The function writes the run artifacts in place.
    """
    run_dir = model_root / model_name / "2605230000"
    run_dir.mkdir(parents=True)
    write_pickle(run_dir / "model.joblib", StubRuntimeModel(probabilities))
    (run_dir / "config.json").write_text(
        json.dumps({"model_name": model_name, "model_config": {"threshold": 0.5}}),
        encoding="utf-8",
    )
    if f1 is not None:
        (run_dir / "metrics.json").write_text(json.dumps({"f1": f1}), encoding="utf-8")


def test_runtime_consensus_eval_compares_weighted_majority_and_any_blog(tmp_path: Path) -> None:
    """Runtime consensus evaluation should expose metrics for all strategies."""
    dataset_dir = tmp_path / "dataset"
    model_root = tmp_path / "runtime" / "current"
    output_dir = tmp_path / "out"
    _write_dataset(dataset_dir)
    _write_runtime_model(model_root, "weak_old", [0.10, 0.90], f1=0.10)
    _write_runtime_model(model_root, "strong_new", [0.80, 0.10], f1=0.95)

    summary = run_evaluate_runtime_consensus(
        dataset_dir=dataset_dir,
        model_root=model_root,
        output_dir=output_dir,
    )

    assert summary["metrics"]["weighted_average"]["f1"] == 1.0
    assert summary["metrics"]["majority_blog"]["f1"] == 0.666667
    assert summary["metrics"]["any_blog"]["precision"] == 0.5
    assert summary["models"][0]["weight"] == 0.95
    assert Path(summary["predictions_path"]).exists()
    assert Path(summary["summary_path"]).exists()


def test_runtime_consensus_eval_can_tune_weighted_threshold_on_validation_split(tmp_path: Path) -> None:
    """Weighted consensus should support validation-selected threshold tuning."""
    dataset_dir = tmp_path / "dataset"
    model_root = tmp_path / "runtime" / "current"
    output_dir = tmp_path / "out"
    _write_dataset(dataset_dir)
    _write_runtime_model(model_root, "weak_old", [0.10, 0.90], f1=0.10)
    _write_runtime_model(model_root, "strong_new", [0.80, 0.10], f1=0.95)

    summary = run_evaluate_runtime_consensus(
        dataset_dir=dataset_dir,
        model_root=model_root,
        output_dir=output_dir,
        strategies=("weighted_average",),
        consensus_threshold=0.9,
        tune_weighted_threshold_split="val",
    )

    assert summary["threshold_tuning"]["split"] == "val"
    assert summary["threshold_tuning"]["val_f1"] == 1.0
    assert summary["consensus_threshold"] < 0.9
    assert summary["metrics"]["weighted_average"]["f1"] == 1.0
