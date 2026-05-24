"""Evaluate whether runtime and graph predictions can support fusion."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from trainer.evaluation.metrics import compute_metrics
from trainer.io.artifact_writer import ensure_dir
from trainer.io.artifact_writer import write_csv
from trainer.io.artifact_writer import write_json
from trainer.models.inference import PredictionRow


DEFAULT_MIN_OVERLAP_FOR_FUSION = 50


def _read_csv(path: Path) -> list[dict[str, str]]:
    """Read a CSV artifact into dictionaries.

    Args:
        path: CSV file to read.

    Returns:
        Row dictionaries keyed by CSV header.
    """
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _candidate_keys(row: dict[str, str]) -> set[str]:
    """Build normalized-ish join keys for prediction artifacts.

    Args:
        row: CSV row from runtime or graph prediction output.

    Returns:
        Non-empty URL/sample identifiers that can be used for conservative
        artifact joining.
    """
    keys: set[str] = set()
    for field in ("normalized_url", "url", "sample_id"):
        value = row.get(field, "").strip()
        if value:
            keys.add(value.rstrip("/"))
            keys.add(value)
    return keys


def _index_runtime_rows(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    """Index runtime prediction rows by URL-like keys.

    Args:
        rows: Runtime consensus prediction rows.

    Returns:
        Mapping from candidate join key to runtime row.
    """
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        for key in _candidate_keys(row):
            indexed.setdefault(key, row)
    return indexed


def _prediction_row(
    *,
    source: dict[str, str],
    pred_label: str,
    prob_blog: float,
) -> PredictionRow:
    """Convert one overlap row into shared metric input.

    Args:
        source: Runtime prediction row containing gold/sample metadata.
        pred_label: Predicted label for the model being evaluated.
        prob_blog: Blog probability or comparable score.

    Returns:
        ``PredictionRow`` compatible with trainer metric helpers.
    """
    return PredictionRow(
        sample_id=source.get("sample_id", source.get("url", "")),
        url=source.get("url", ""),
        title=source.get("title", ""),
        domain="",
        raw_labels=[],
        gold_label=source["gold_label"],
        pred_label=pred_label,
        prob_blog=prob_blog,
        split="overlap",
    )


def run_evaluate_graph_runtime_overlap(
    *,
    runtime_predictions: Path,
    graph_predictions: Path,
    output_dir: Path,
    graph_split: str = "test",
    runtime_strategy: str = "weighted_average",
    min_overlap_for_fusion: int = DEFAULT_MIN_OVERLAP_FOR_FUSION,
) -> dict[str, Any]:
    """Measure whether runtime and graph prediction artifacts align enough.

    Args:
        runtime_predictions: CSV produced by ``evaluate-runtime-consensus``.
        graph_predictions: GCN ``predictions_labeled.csv`` artifact.
        output_dir: Directory where summary and overlap rows are written.
        graph_split: Graph split to compare, usually ``test``.
        runtime_strategy: Runtime consensus strategy column prefix to compare.
        min_overlap_for_fusion: Minimum overlap count required before reporting
            fusion as trustworthy.

    Returns:
        Serializable overlap summary and artifact paths.
    """
    runtime_rows = _read_csv(runtime_predictions)
    graph_rows = [row for row in _read_csv(graph_predictions) if row.get("split") == graph_split]
    runtime_index = _index_runtime_rows(runtime_rows)

    overlap_rows: list[dict[str, Any]] = []
    runtime_metric_rows: list[PredictionRow] = []
    graph_metric_rows: list[PredictionRow] = []
    runtime_label_field = f"{runtime_strategy}_label"
    runtime_score_field = f"{runtime_strategy}_score"

    for graph_row in graph_rows:
        runtime_row = next((runtime_index[key] for key in _candidate_keys(graph_row) if key in runtime_index), None)
        if runtime_row is None:
            continue
        runtime_score = float(runtime_row.get(runtime_score_field, 0.0))
        graph_score = float(graph_row.get("prob_blog", 0.0))
        runtime_label = runtime_row[runtime_label_field]
        graph_label = graph_row["pred_label"]
        runtime_metric_rows.append(
            _prediction_row(source=runtime_row, pred_label=runtime_label, prob_blog=runtime_score)
        )
        graph_metric_rows.append(
            _prediction_row(source=runtime_row, pred_label=graph_label, prob_blog=graph_score)
        )
        overlap_rows.append(
            {
                "url": runtime_row.get("url", graph_row.get("url", "")),
                "title": runtime_row.get("title", graph_row.get("title", "")),
                "gold_label": runtime_row["gold_label"],
                "runtime_label": runtime_label,
                "runtime_score": runtime_score,
                "graph_label": graph_label,
                "graph_score": graph_score,
            }
        )

    output_dir = ensure_dir(output_dir)
    overlap_path = output_dir / "graph_runtime_overlap.csv"
    summary_path = output_dir / "graph_runtime_overlap_summary.json"
    write_csv(
        overlap_path,
        fieldnames=[
            "url",
            "title",
            "gold_label",
            "runtime_label",
            "runtime_score",
            "graph_label",
            "graph_score",
        ],
        rows=overlap_rows,
    )
    summary: dict[str, Any] = {
        "runtime_predictions": str(runtime_predictions),
        "graph_predictions": str(graph_predictions),
        "graph_split": graph_split,
        "runtime_strategy": runtime_strategy,
        "runtime_count": len(runtime_rows),
        "graph_split_count": len(graph_rows),
        "overlap_count": len(overlap_rows),
        "min_overlap_for_fusion": min_overlap_for_fusion,
        "fusion_allowed": len(overlap_rows) >= min_overlap_for_fusion,
        "runtime_overlap_metrics": compute_metrics(runtime_metric_rows) if runtime_metric_rows else {},
        "graph_overlap_metrics": compute_metrics(graph_metric_rows) if graph_metric_rows else {},
        "overlap_path": str(overlap_path),
        "summary_path": str(summary_path),
    }
    write_json(summary_path, summary)
    return summary
