"""Tests for runtime/graph prediction overlap evaluation."""

from __future__ import annotations

from pathlib import Path

from trainer.io.artifact_writer import write_csv
from trainer.pipelines.evaluate_graph_runtime_overlap import run_evaluate_graph_runtime_overlap


def test_graph_runtime_overlap_blocks_fusion_when_overlap_is_too_small(tmp_path: Path) -> None:
    """Overlap evaluation should prevent fusion claims on tiny shared samples."""
    runtime_predictions = tmp_path / "runtime.csv"
    graph_predictions = tmp_path / "graph.csv"
    output_dir = tmp_path / "out"
    write_csv(
        runtime_predictions,
        fieldnames=[
            "sample_id",
            "url",
            "title",
            "gold_label",
            "weighted_average_label",
            "weighted_average_score",
        ],
        rows=[
            {
                "sample_id": "https://blog.example/",
                "url": "https://blog.example/",
                "title": "Blog",
                "gold_label": "blog",
                "weighted_average_label": "blog",
                "weighted_average_score": 0.8,
            },
            {
                "sample_id": "https://company.example/",
                "url": "https://company.example/",
                "title": "Company",
                "gold_label": "non_blog",
                "weighted_average_label": "non_blog",
                "weighted_average_score": 0.1,
            },
        ],
    )
    write_csv(
        graph_predictions,
        fieldnames=["url", "title", "normalized_url", "split", "gold_label", "pred_label", "prob_blog"],
        rows=[
            {
                "url": "https://blog.example/",
                "title": "Blog",
                "normalized_url": "https://blog.example/",
                "split": "test",
                "gold_label": "blog",
                "pred_label": "blog",
                "prob_blog": 0.7,
            },
            {
                "url": "https://other.example/",
                "title": "Other",
                "normalized_url": "https://other.example/",
                "split": "test",
                "gold_label": "non_blog",
                "pred_label": "blog",
                "prob_blog": 0.9,
            },
        ],
    )

    summary = run_evaluate_graph_runtime_overlap(
        runtime_predictions=runtime_predictions,
        graph_predictions=graph_predictions,
        output_dir=output_dir,
        min_overlap_for_fusion=2,
    )

    assert summary["runtime_count"] == 2
    assert summary["graph_split_count"] == 2
    assert summary["overlap_count"] == 1
    assert summary["fusion_allowed"] is False
    assert summary["runtime_overlap_metrics"]["f1"] == 1.0
    assert summary["graph_overlap_metrics"]["f1"] == 1.0
    assert Path(summary["overlap_path"]).exists()
    assert Path(summary["summary_path"]).exists()
