"""Write crawler graph exports in CSV and JSON formats."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from persistence_api.graph_projection import build_graph_snapshot_payload
from persistence_api.graph_projection import write_snapshot_files
from persistence_api.repository import RepositoryProtocol


class ExportService:
    """Persist graph snapshots for downstream analysis tools."""

    def __init__(self, repository: RepositoryProtocol, export_dir: Path) -> None:
        """Create an exporter bound to a repository and output folder."""
        self.repository = repository
        self.export_dir = export_dir

    def write_exports(self) -> dict[str, str]:
        """Write nodes/edges CSV and combined graph JSON files."""
        self.export_dir.mkdir(parents=True, exist_ok=True)
        nodes_path = self.export_dir / "nodes.csv"
        edges_path = self.export_dir / "edges.csv"
        graph_path = self.export_dir / "graph.json"

        blogs: list[dict[str, Any]] = self.repository.list_blogs()
        edges: list[dict[str, Any]] = self.repository.list_edges()

        with nodes_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(blogs[0].keys()) if blogs else ["id"])
            writer.writeheader()
            writer.writerows(blogs)

        with edges_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(edges[0].keys()) if edges else ["id"])
            writer.writeheader()
            writer.writerows(edges)

        with graph_path.open("w", encoding="utf-8") as handle:
            json.dump({"nodes": blogs, "edges": edges}, handle, ensure_ascii=False, indent=2)

        snapshot_payload = build_graph_snapshot_payload(blogs, edges)
        snapshot_paths = write_snapshot_files(self.export_dir, snapshot_payload)

        return {
            "nodes_csv": str(nodes_path),
            "edges_csv": str(edges_path),
            "graph_json": str(graph_path),
            **snapshot_paths,
        }
