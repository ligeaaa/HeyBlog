"""Evaluate one trained run and write report artifacts."""

from __future__ import annotations

from pathlib import Path

from trainer.dataset.schema import SupervisedSample
from trainer.evaluation.confusion import build_confusion_matrix
from trainer.evaluation.error_analysis import build_top_errors
from trainer.evaluation.metrics import compute_confusion_counts
from trainer.evaluation.metrics import compute_metrics
from trainer.evaluation.reports import build_run_report
from trainer.io.artifact_writer import write_csv
from trainer.io.artifact_writer import write_json
from trainer.io.artifact_writer import write_text
from trainer.io.dataset_reader import read_json
from trainer.io.dataset_reader import read_jsonl
from trainer.models.inference import build_prediction_rows
from trainer.models.inference import load_model


def _deserialize_samples(rows: list[dict[str, object]]) -> list[SupervisedSample]:
    return [SupervisedSample(**row) for row in rows]


def run_evaluate_run(*, run_dir: Path) -> dict[str, object]:
    config = read_json(run_dir / "config.json")
    dataset_dir = Path(config["dataset_dir"])
    model = load_model(run_dir / "model.joblib")
    test_samples = _deserialize_samples(read_jsonl(dataset_dir / "test.jsonl"))
    probabilities = model.predict_proba(test_samples)
    predictions = build_prediction_rows(test_samples, probabilities, threshold=model.threshold)
    metrics = compute_metrics(predictions)
    confusion = build_confusion_matrix(compute_confusion_counts(predictions))
    top_errors = build_top_errors(predictions)
    dataset_stats = read_json(dataset_dir / "dataset_stats.json")
    split_manifest = read_json(dataset_dir / "split_manifest.json")

    write_json(run_dir / "metrics.json", metrics)
    write_json(run_dir / "confusion_matrix.json", confusion)
    write_csv(
        run_dir / "predictions_test.csv",
        fieldnames=["sample_id", "url", "title", "domain", "raw_labels", "gold_label", "pred_label", "prob_blog", "split"],
        rows=[row.to_dict() for row in predictions],
    )
    write_csv(
        run_dir / "top_errors.csv",
        fieldnames=["sample_id", "url", "title", "domain", "raw_labels", "gold_label", "pred_label", "prob_blog", "split", "error_type", "confidence"],
        rows=top_errors,
    )
    write_text(
        run_dir / "report.md",
        build_run_report(
            model_name=config["model_name"],
            dataset_dir=dataset_dir,
            metrics=metrics,
            dataset_stats=dataset_stats,
            split_manifest=split_manifest,
        ),
    )
    return {
        "run_dir": str(run_dir),
        "model_name": config["model_name"],
        "metrics": metrics,
    }
