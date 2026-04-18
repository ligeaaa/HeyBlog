"""Assemble graph payloads, views, and snapshots inside persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from persistence_api.age_graph import AgeGraphManager
from persistence_api.graph_projection import build_core_graph_view
from persistence_api.graph_projection import build_graph_snapshot_payload
from persistence_api.graph_projection import build_neighborhood_graph_view
from persistence_api.graph_projection import load_snapshot_manifest
from persistence_api.graph_projection import load_snapshot_payload
from persistence_api.graph_projection import latest_snapshot_manifest_filename
from persistence_api.repository import RepositoryProtocol
from persistence_api.graph_projection import write_snapshot_files


class GraphService:
    """Create combined node-edge graph views from repository data."""

    def __init__(
        self,
        repository: RepositoryProtocol,
        export_dir: Path,
        *,
        graph_backend: str = "legacy",
        snapshot_namespace: str = "legacy",
        age_manager: AgeGraphManager | None = None,
    ) -> None:
        """Store repository dependency for graph reads."""
        self.repository = repository
        self.export_dir = export_dir
        self.configured_graph_backend = graph_backend
        self.graph_backend = "legacy"
        self.snapshot_namespace = snapshot_namespace
        self.age_manager = age_manager

    def graph_status(self) -> dict[str, Any]:
        """Return graph-read backend readiness details."""
        if self.age_manager is None:
            return {
                "graph_backend": self.graph_backend,
                "configured_graph_backend": self.configured_graph_backend,
                "age_enabled": False,
                "age_sync_state": "not_configured",
                "parity_status": "unknown",
                "latest_snapshot_namespace": self.snapshot_namespace,
                "latest_snapshot_manifest": latest_snapshot_manifest_filename(self.snapshot_namespace),
                "last_error": None,
            }
        return self.age_manager.status(
            graph_backend=self.graph_backend,
            snapshot_namespace=self.snapshot_namespace,
        ) | {
            "configured_graph_backend": self.configured_graph_backend,
            "latest_snapshot_manifest": latest_snapshot_manifest_filename(self.snapshot_namespace),
        }

    def rebuild_shadow_graph(self) -> dict[str, Any]:
        """Rebuild the optional AGE shadow graph out of band from read requests."""
        blogs = self.repository.list_blogs()
        edges = self.repository.list_edges()
        if self.age_manager is None:
            return self.graph_status()
        self.age_manager.sync_shadow_graph(blogs, edges)
        return self.graph_status()

    def graph_view(
        self,
        *,
        strategy: str = "degree",
        limit: int = 180,
        sample_mode: str = "off",
        sample_value: float | None = None,
        sample_seed: int = 7,
    ) -> dict[str, Any]:
        """Return the default graph explorer view."""
        snapshot = self._fresh_snapshot_payload()
        return build_core_graph_view(
            snapshot,
            strategy=strategy,
            limit=limit,
            sample_mode=sample_mode,
            sample_value=sample_value,
            sample_seed=sample_seed,
        )

    def graph_neighbors(self, *, node_id: int, hops: int = 1, limit: int = 120) -> dict[str, Any]:
        """Return one node neighborhood from the latest stable snapshot."""
        snapshot = self._fresh_snapshot_payload()
        return build_neighborhood_graph_view(snapshot, node_id=node_id, hops=hops, limit=limit)

    def latest_snapshot_manifest(self) -> dict[str, Any]:
        """Return the latest snapshot manifest, refreshing it when the graph changed."""
        self._fresh_snapshot_payload()
        manifest = load_snapshot_manifest(self.export_dir, namespace=self.snapshot_namespace)
        assert manifest is not None
        return manifest

    def snapshot(self, version: str) -> dict[str, Any] | None:
        """Return a versioned snapshot payload when present."""
        payload = self._fresh_snapshot_payload()
        if str(payload["version"]) == version:
            return payload
        return load_snapshot_payload(self.export_dir, version, namespace=self.snapshot_namespace)

    def _latest_snapshot_payload(self) -> dict[str, Any]:
        return self._fresh_snapshot_payload()

    def _fresh_snapshot_payload(self) -> dict[str, Any]:
        manifest = load_snapshot_manifest(self.export_dir, namespace=self.snapshot_namespace)
        snapshot = self._live_snapshot_payload(source="snapshot")
        graph_fingerprint = snapshot["meta"].get("graph_fingerprint")

        if manifest is not None and manifest.get("graph_fingerprint") == graph_fingerprint:
            version = str(manifest["version"])
            payload = load_snapshot_payload(self.export_dir, version, namespace=self.snapshot_namespace)
            if payload is not None and payload.get("meta", {}).get("graph_fingerprint") == graph_fingerprint:
                return payload

        write_snapshot_files(self.export_dir, snapshot, namespace=self.snapshot_namespace)
        return snapshot

    def _live_snapshot_payload(self, *, source: str) -> dict[str, Any]:
        blogs = self.repository.list_blogs()
        edges = self.repository.list_edges()
        return build_graph_snapshot_payload(
            blogs,
            edges,
            source=f"{self.graph_backend}:{source}",
            snapshot_namespace=self.snapshot_namespace,
        )
