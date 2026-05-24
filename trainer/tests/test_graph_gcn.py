"""Smoke tests for graph GCN dataset loading and training."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from trainer.graph.dataset import load_graph_dataset
from trainer.graph.pipeline import run_train_gcn


def _write_fixture_dataset(path: Path) -> None:
    path.mkdir(parents=True)
    nodes = []
    labels = []
    for index in range(40):
        is_blog = index < 20
        domain = f"{'blog' if is_blog else 'company'}-{index}.example"
        url = f"https://{domain}/"
        nodes.append(
            {
                "id": index + 1,
                "blog_id": index + 1,
                "url": url,
                "normalized_url": url,
                "domain": domain,
                "title": f"{'Personal blog notes' if is_blog else 'Company official site'} {index}",
                "crawl_status": "FINISHED",
            }
        )
        labels.append({"url": url, "title": nodes[-1]["title"], "label": "blog" if is_blog else "company"})
    edges = []
    edge_id = 1
    for start in (1, 21):
        for offset in range(19):
            edges.append(
                {
                    "id": edge_id,
                    "from_blog_id": start + offset,
                    "to_blog_id": start + offset + 1,
                    "link_url_raw": nodes[start + offset]["url"],
                    "link_text": "",
                    "discovered_at": "2026-01-01T00:00:00Z",
                }
            )
            edge_id += 1
    (path / "graph.json").write_text(json.dumps({"nodes": nodes, "edges": edges}), encoding="utf-8")
    with (path / "labels.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["url", "title", "label"])
        writer.writeheader()
        writer.writerows(labels)


def test_load_graph_dataset_builds_splits(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    _write_fixture_dataset(dataset_dir)

    dataset = load_graph_dataset(dataset_dir=dataset_dir, max_features=128, seed=7)

    assert dataset.metadata["graph_nodes"] == 40
    assert dataset.metadata["labeled_nodes"] == 40
    assert dataset.split_masks["train"].sum() > dataset.split_masks["val"].sum()
    assert dataset.features.shape[0] == 40
    assert "graph_degree_metadata" in dataset.metadata["feature_sources"]


def test_load_graph_dataset_supports_self_loop_ablation(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    _write_fixture_dataset(dataset_dir)

    dataset = load_graph_dataset(dataset_dir=dataset_dir, max_features=128, seed=7, graph_mode="self_loop")

    assert dataset.metadata["graph_mode"] == "self_loop"
    assert dataset.metadata["adjacency_edges"] == 0
    assert dataset.adjacency.nnz == dataset.metadata["graph_nodes"]


def test_run_train_gcn_writes_metrics(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    output_dir = tmp_path / "run"
    _write_fixture_dataset(dataset_dir)

    payload = run_train_gcn(
        dataset_dir=dataset_dir,
        output_dir=output_dir,
        max_features=128,
        hidden_dim=16,
        layers=2,
        epochs=3,
        patience=2,
        graph_mode="dropout",
        edge_dropout=0.5,
    )

    assert payload["model_name"] == "gcn"
    assert (output_dir / "metrics.json").exists()
    assert (output_dir / "predictions_labeled.csv").exists()
    assert payload["metrics"]["test"]["count"] > 0
    assert payload["dataset_summary"]["graph_mode"] == "dropout"
