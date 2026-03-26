from __future__ import annotations

import csv
import json
from pathlib import Path

from app.db.repository import Repository


class ExportService:
    def __init__(self, repository: Repository, export_dir: Path) -> None:
        self.repository = repository
        self.export_dir = export_dir

    def write_exports(self) -> dict[str, str]:
        self.export_dir.mkdir(parents=True, exist_ok=True)
        nodes_path = self.export_dir / "nodes.csv"
        edges_path = self.export_dir / "edges.csv"
        graph_path = self.export_dir / "graph.json"

        blogs = self.repository.list_blogs()
        edges = self.repository.list_edges()

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

        return {
            "nodes_csv": str(nodes_path),
            "edges_csv": str(edges_path),
            "graph_json": str(graph_path),
        }
