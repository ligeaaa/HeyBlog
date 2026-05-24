"""End-to-end GCN graph training pipeline."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch

from trainer.graph.dataset import GraphDataset
from trainer.graph.dataset import load_graph_dataset
from trainer.graph.gcn import GCNTrainingConfig
from trainer.graph.gcn import compute_binary_metrics
from trainer.graph.gcn import train_gcn
from trainer.io.artifact_writer import ensure_dir
from trainer.io.artifact_writer import write_csv
from trainer.io.artifact_writer import write_json
from trainer.io.artifact_writer import write_text


def default_graph_run_id() -> str:
    """Return a timestamp identifier for one graph model run."""
    return datetime.now(timezone.utc).strftime("%y%m%d%H%M")


def _split_metrics(
    dataset: GraphDataset,
    probabilities: np.ndarray,
    *,
    threshold: float,
) -> dict[str, dict[str, Any]]:
    metrics = {}
    for split, mask in dataset.split_masks.items():
        labels = dataset.labels[mask]
        probs = probabilities[mask]
        metrics[split] = compute_binary_metrics(labels, probs, threshold=threshold)
        metrics[split]["count"] = int(mask.sum())
    return metrics


def _prediction_rows(
    dataset: GraphDataset,
    probabilities: np.ndarray,
    *,
    threshold: float,
) -> list[dict[str, Any]]:
    split_by_index: dict[int, str] = {}
    for split, mask in dataset.split_masks.items():
        for index in np.flatnonzero(mask):
            split_by_index[int(index)] = split
    rows = []
    for index in dataset.labeled_indices.tolist():
        probability = float(probabilities[index])
        gold = int(dataset.labels[index])
        pred = 1 if probability >= threshold else 0
        rows.append(
            {
                "node_index": index,
                "node_id": dataset.node_ids[index],
                "url": dataset.urls[index],
                "title": dataset.titles[index],
                "normalized_url": dataset.normalized_urls[index],
                "split": split_by_index.get(index, "unassigned"),
                "gold_label": "blog" if gold == 1 else "non_blog",
                "pred_label": "blog" if pred == 1 else "non_blog",
                "prob_blog": round(probability, 6),
                "is_error": gold != pred,
            }
        )
    return rows


def _build_report(*, dataset: GraphDataset, metrics: dict[str, Any], run_dir: Path) -> str:
    test_metrics = metrics["splits"]["test"]
    lines = [
        "# Graph GCN Report",
        "",
        f"- Run dir: `{run_dir}`",
        f"- Dataset dir: `{dataset.metadata['dataset_dir']}`",
        f"- Graph nodes: `{dataset.metadata['graph_nodes']}`",
        f"- Graph edges: `{dataset.metadata['graph_edges']}`",
        f"- Labeled graph nodes: `{dataset.metadata['labeled_nodes']}`",
        f"- Feature shape: `{dataset.metadata['feature_shape']}`",
        "",
        "## Test Metrics",
        "",
        f"- Precision: `{test_metrics['precision']}`",
        f"- Recall: `{test_metrics['recall']}`",
        f"- F1: `{test_metrics['f1']}`",
        f"- PR-AUC: `{test_metrics['pr_auc']}`",
        f"- ROC-AUC: `{test_metrics['roc_auc']}`",
        f"- Accuracy: `{test_metrics['accuracy']}`",
        f"- TP/FP/TN/FN: `{test_metrics['tp']}/{test_metrics['fp']}/{test_metrics['tn']}/{test_metrics['fn']}`",
        "",
        "## Notes",
        "",
        "- This residual GCN uses URL/title/metadata TF-IDF, structured blog/page signals, graph-degree metadata, and graph message passing over the exported HeyBlog graph.",
        "- Metrics are graph-in only: nodes must overlap `labels.csv` and `graph.json` to participate in supervised evaluation.",
    ]
    return "\n".join(lines) + "\n"


def run_train_gcn(
    *,
    dataset_dir: Path,
    output_dir: Path | None = None,
    max_features: int = 4096,
    hidden_dim: int = 64,
    layers: int = 3,
    epochs: int = 200,
    learning_rate: float = 0.01,
    weight_decay: float = 5e-4,
    dropout: float = 0.35,
    patience: int = 25,
    seed: int = 7,
    graph_mode: str = "full",
    edge_dropout: float = 0.0,
) -> dict[str, Any]:
    """Train and evaluate a simple GCN from exported graph dataset files.

    Args:
        dataset_dir: Directory containing ``labels.csv`` and ``graph.json``.
        output_dir: Optional run output directory.
        max_features: Maximum TF-IDF feature count.
        hidden_dim: GCN hidden dimension.
        layers: Number of residual graph message-passing layers.
        epochs: Maximum training epochs.
        learning_rate: Adam learning rate.
        weight_decay: Adam weight decay.
        dropout: Dropout probability.
        patience: Early stopping patience on validation F1.
        seed: Random seed.
        graph_mode: Graph ablation mode: ``full``, ``self_loop``, or ``dropout``.
        edge_dropout: Fraction of raw graph edges dropped when
            ``graph_mode='dropout'``.

    Returns:
        Serializable run summary including metrics and output paths.
    """
    dataset = load_graph_dataset(
        dataset_dir=dataset_dir,
        max_features=max_features,
        seed=seed,
        graph_mode=graph_mode,
        edge_dropout=edge_dropout,
    )
    config = GCNTrainingConfig(
        seed=seed,
        hidden_dim=hidden_dim,
        layers=layers,
        epochs=epochs,
        learning_rate=learning_rate,
        weight_decay=weight_decay,
        dropout=dropout,
        patience=patience,
    )
    model, training_summary, probabilities = train_gcn(dataset, config)
    run_dir = ensure_dir(output_dir or Path("data/model/gcn") / default_graph_run_id())
    selected_threshold = float(training_summary.get("selected_threshold", 0.5))
    metrics = {
        "splits": _split_metrics(dataset, probabilities, threshold=selected_threshold),
        "training": training_summary,
    }
    predictions = _prediction_rows(dataset, probabilities, threshold=selected_threshold)
    write_json(run_dir / "dataset_summary.json", dataset.metadata)
    write_json(run_dir / "metrics.json", metrics)
    write_json(run_dir / "config.json", {"dataset_dir": str(dataset_dir), "model_name": "gcn", "config": asdict(config)})
    write_csv(
        run_dir / "predictions_labeled.csv",
        fieldnames=[
            "node_index",
            "node_id",
            "url",
            "title",
            "normalized_url",
            "split",
            "gold_label",
            "pred_label",
            "prob_blog",
            "is_error",
        ],
        rows=predictions,
    )
    write_text(run_dir / "report.md", _build_report(dataset=dataset, metrics=metrics, run_dir=run_dir))
    torch.save(model.state_dict(), run_dir / "model.pt")
    return {
        "run_dir": str(run_dir),
        "model_name": "gcn",
        "dataset_dir": str(dataset_dir),
        "metrics": metrics["splits"],
        "dataset_summary": dataset.metadata,
    }
