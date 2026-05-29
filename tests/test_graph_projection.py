"""Tests for graph views and offline snapshot projections."""

from datetime import UTC
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

from persistence_api.graph_service import GraphService
from persistence_api.graph_projection import build_core_graph_view
from persistence_api.graph_projection import build_graph_snapshot_payload
from persistence_api.graph_projection import build_neighborhood_graph_view
from persistence_api.graph_projection import load_snapshot_manifest
from persistence_api.graph_projection import load_snapshot_payload
from persistence_api.graph_projection import write_snapshot_files
from persistence_api.graph_projection import latest_snapshot_manifest_filename
from persistence_api.graph_projection import snapshot_filename


def sample_graph() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    blogs = [
        {
            "id": 1,
            "url": "https://alpha.example",
            "normalized_url": "https://alpha.example",
            "domain": "alpha.example",
            "title": "Alpha Blog",
            "icon_url": "https://alpha.example/favicon.ico",
            "status_code": 200,
            "crawl_status": "FINISHED",
            "friend_links_count": 3,
            "last_crawled_at": None,
            "created_at": "2026-03-31T00:00:00Z",
            "updated_at": "2026-03-31T00:00:00Z",
        },
        {
            "id": 2,
            "url": "https://beta.example",
            "normalized_url": "https://beta.example",
            "domain": "beta.example",
            "title": "Beta Blog",
            "icon_url": "https://beta.example/favicon.ico",
            "status_code": 200,
            "crawl_status": "FINISHED",
            "friend_links_count": 2,
            "last_crawled_at": None,
            "created_at": "2026-03-31T00:00:00Z",
            "updated_at": "2026-03-31T00:00:00Z",
        },
        {
            "id": 3,
            "url": "https://gamma.example",
            "normalized_url": "https://gamma.example",
            "domain": "gamma.example",
            "title": None,
            "icon_url": None,
            "status_code": 200,
            "crawl_status": "FINISHED",
            "friend_links_count": 1,
            "last_crawled_at": None,
            "created_at": "2026-03-31T00:00:00Z",
            "updated_at": "2026-03-31T00:00:00Z",
        },
    ]
    edges = [
        {
            "id": 11,
            "from_blog_id": 1,
            "to_blog_id": 2,
            "link_url_raw": "https://beta.example",
            "link_text": "beta",
            "discovered_at": "2026-03-31T00:00:00Z",
        },
        {
            "id": 12,
            "from_blog_id": 2,
            "to_blog_id": 3,
            "link_url_raw": "https://gamma.example",
            "link_text": "gamma",
            "discovered_at": "2026-03-31T00:00:00Z",
        },
    ]
    return blogs, edges


def test_snapshot_payload_contains_stable_positions() -> None:
    blogs, edges = sample_graph()

    payload = build_graph_snapshot_payload(blogs, edges, version="v1", generated_at="2026-03-31T00:00:00Z")

    assert payload["version"] == "v1"
    assert payload["meta"]["has_stable_positions"] is True
    assert payload["meta"]["graph_fingerprint"]
    node_by_id = {node["id"]: node for node in payload["nodes"]}
    assert node_by_id[1]["x"] is not None
    assert node_by_id[1]["component_id"].startswith("component-")
    assert node_by_id[1]["title"] == "Alpha Blog"
    assert node_by_id[1]["icon_url"] == "https://alpha.example/favicon.ico"


def test_core_view_sampling_is_deterministic() -> None:
    blogs, edges = sample_graph()
    snapshot = build_graph_snapshot_payload(blogs, edges, version="v1", generated_at="2026-03-31T00:00:00Z")

    first = build_core_graph_view(
        snapshot,
        strategy="degree",
        limit=2,
        sample_mode="count",
        sample_value=2,
        sample_seed=17,
    )
    second = build_core_graph_view(
        snapshot,
        strategy="degree",
        limit=2,
        sample_mode="count",
        sample_value=2,
        sample_seed=17,
    )

    assert [node["id"] for node in first["nodes"]] == [node["id"] for node in second["nodes"]]
    assert first["meta"]["sampled"] is True


def test_core_view_count_sampling_expands_from_random_seed_by_bfs() -> None:
    blogs, edges = sample_graph()
    for blog_id in range(4, 7):
        blogs.append(
            {
                "id": blog_id,
                "url": f"https://extra-{blog_id}.example",
                "normalized_url": f"https://extra-{blog_id}.example",
                "domain": f"extra-{blog_id}.example",
                "title": f"Extra {blog_id}",
                "icon_url": None,
                "status_code": 200,
                "crawl_status": "FINISHED",
                "friend_links_count": 0,
                "last_crawled_at": None,
                "created_at": "2026-03-31T00:00:00Z",
                "updated_at": "2026-03-31T00:00:00Z",
            },
        )
    edges.extend(
        [
            {
                "id": 13,
                "from_blog_id": 4,
                "to_blog_id": 5,
                "link_url_raw": "https://extra-5.example",
                "link_text": "extra 5",
                "discovered_at": "2026-03-31T00:00:00Z",
            },
            {
                "id": 14,
                "from_blog_id": 5,
                "to_blog_id": 6,
                "link_url_raw": "https://extra-6.example",
                "link_text": "extra 6",
                "discovered_at": "2026-03-31T00:00:00Z",
            },
        ],
    )
    snapshot = build_graph_snapshot_payload(blogs, edges, version="v1", generated_at="2026-03-31T00:00:00Z")

    payload = build_core_graph_view(
        snapshot,
        strategy="degree",
        limit=3,
        sample_mode="count",
        sample_value=3,
        sample_seed=42,
    )

    assert payload["meta"]["strategy"] == "sampled_bfs"
    assert payload["meta"]["sampled"] is True
    assert {node["id"] for node in payload["nodes"]} == {4, 5, 6}
    assert {edge["id"] for edge in payload["edges"]} == {13, 14}


def test_core_view_seed_strategy_prefers_oldest_nodes() -> None:
    blogs, edges = sample_graph()
    snapshot = build_graph_snapshot_payload(blogs, edges, version="v1", generated_at="2026-03-31T00:00:00Z")

    payload = build_core_graph_view(snapshot, strategy="seed", limit=2)

    assert payload["meta"]["strategy"] == "seed"
    assert {node["id"] for node in payload["nodes"][:2]} == {1, 2}


def test_core_view_allows_ten_thousand_node_limit() -> None:
    blogs, edges = sample_graph()
    snapshot = build_graph_snapshot_payload(blogs, edges, version="v1", generated_at="2026-03-31T00:00:00Z")

    payload = build_core_graph_view(snapshot, strategy="degree", limit=10_000)

    assert payload["meta"]["limit"] == 10_000
    assert payload["meta"]["selected_nodes"] == 3


def test_core_view_seed_strategy_returns_nodes_without_lineage_metadata() -> None:
    blogs, edges = sample_graph()
    snapshot = build_graph_snapshot_payload(blogs, edges, version="v1", generated_at="2026-03-31T00:00:00Z")

    payload = build_core_graph_view(snapshot, strategy="seed", limit=2)

    assert payload["meta"]["strategy"] == "seed"
    assert payload["nodes"]


def test_neighborhood_view_keeps_focus_node() -> None:
    blogs, edges = sample_graph()
    snapshot = build_graph_snapshot_payload(blogs, edges, version="v1", generated_at="2026-03-31T00:00:00Z")

    payload = build_neighborhood_graph_view(snapshot, node_id=2, hops=1, limit=3)

    assert payload["meta"]["focus_node_id"] == 2
    assert {node["id"] for node in payload["nodes"]} == {1, 2, 3}


def test_snapshot_files_are_written_with_latest_manifest(tmp_path: Path) -> None:
    blogs, edges = sample_graph()
    snapshot = build_graph_snapshot_payload(blogs, edges, version="v1", generated_at="2026-03-31T00:00:00Z")

    paths = write_snapshot_files(tmp_path, snapshot)

    manifest = load_snapshot_manifest(tmp_path)
    payload = load_snapshot_payload(tmp_path, "v1")

    assert Path(paths["graph_snapshot_manifest"]).exists()
    assert Path(paths["graph_snapshot"]).exists()
    assert manifest is not None
    assert manifest["version"] == "v1"
    assert manifest["graph_fingerprint"] == snapshot["meta"]["graph_fingerprint"]
    assert payload is not None
    assert payload["nodes"][0]["x"] is not None


def test_snapshot_files_support_source_namespaces(tmp_path: Path) -> None:
    blogs, edges = sample_graph()
    snapshot = build_graph_snapshot_payload(
        blogs,
        edges,
        version="v1",
        generated_at="2026-03-31T00:00:00Z",
        snapshot_namespace="legacy",
    )

    write_snapshot_files(tmp_path, snapshot, namespace="legacy")

    assert (tmp_path / latest_snapshot_manifest_filename("legacy")).exists()
    assert (tmp_path / snapshot_filename("v1", "legacy")).exists()
    manifest = load_snapshot_manifest(tmp_path, namespace="legacy")
    payload = load_snapshot_payload(tmp_path, "v1", namespace="legacy")
    assert manifest is not None
    assert manifest["snapshot_namespace"] == "legacy"
    assert payload is not None
    assert payload["meta"]["snapshot_namespace"] == "legacy"


def test_snapshot_files_serialize_postgres_style_datetimes(tmp_path: Path) -> None:
    blogs, edges = sample_graph()
    postgres_time = datetime(2026, 3, 31, 0, 0, tzinfo=UTC)
    blogs[0]["created_at"] = postgres_time
    blogs[0]["updated_at"] = postgres_time
    edges[0]["discovered_at"] = postgres_time

    snapshot = build_graph_snapshot_payload(blogs, edges, version="v1", generated_at="2026-03-31T00:00:00Z")

    write_snapshot_files(tmp_path, snapshot)
    payload = load_snapshot_payload(tmp_path, "v1")

    assert payload is not None
    node_by_id = {node["id"]: node for node in payload["nodes"]}
    edge_by_id = {edge["id"]: edge for edge in payload["edges"]}
    assert node_by_id[1]["created_at"] == postgres_time.isoformat()
    assert edge_by_id[11]["discovered_at"] == postgres_time.isoformat()


def test_graph_service_refreshes_snapshot_when_repository_graph_changes(tmp_path: Path) -> None:
    blogs, edges = sample_graph()

    class MutableRepository:
        def __init__(self) -> None:
            self.blogs = [dict(blog) for blog in blogs]
            self.edges = [dict(edge) for edge in edges]

        def list_blogs(self) -> list[dict[str, object]]:
            return [dict(blog) for blog in self.blogs]

        def list_edges(self) -> list[dict[str, object]]:
            return [dict(edge) for edge in self.edges]

    repository = MutableRepository()
    service = GraphService(repository, tmp_path)

    first_view = service.graph_view(limit=10)
    first_manifest = service.latest_snapshot_manifest()

    repository.blogs.append(
        {
            "id": 4,
            "url": "https://delta.example",
            "normalized_url": "https://delta.example",
            "domain": "delta.example",
            "title": "Delta Blog",
            "icon_url": "https://delta.example/favicon.ico",
            "status_code": 200,
            "crawl_status": "FINISHED",
            "friend_links_count": 2,
            "last_crawled_at": None,
            "created_at": "2026-03-31T00:05:00Z",
            "updated_at": "2026-03-31T00:05:00Z",
        }
    )
    repository.edges.append(
        {
            "id": 13,
            "from_blog_id": 1,
            "to_blog_id": 4,
            "link_url_raw": "https://delta.example",
            "link_text": "delta",
            "discovered_at": "2026-03-31T00:05:00Z",
        }
    )

    second_view = service.graph_view(limit=10)
    second_manifest = service.latest_snapshot_manifest()

    assert first_view["meta"]["available_nodes"] == 3
    assert second_view["meta"]["available_nodes"] == 4
    assert first_manifest["graph_fingerprint"] != second_manifest["graph_fingerprint"]
    assert first_manifest["version"] != second_manifest["version"]


def test_graph_service_reports_configured_backend_and_skips_age_reads_when_unconfigured(tmp_path: Path) -> None:
    """Graph status should preserve the configured backend without forcing repository reads."""

    class ExplodingRepository:
        def list_blogs(self) -> list[dict[str, object]]:
            raise AssertionError("repository should not be read when AGE is disabled")

        def list_edges(self) -> list[dict[str, object]]:
            raise AssertionError("repository should not be read when AGE is disabled")

    service = GraphService(ExplodingRepository(), tmp_path, graph_backend="age")

    assert service.graph_status()["graph_backend"] == "age"
    assert service.rebuild_shadow_graph()["configured_graph_backend"] == "age"


def test_graph_service_rebuilds_shadow_graph_when_age_manager_is_present(tmp_path: Path) -> None:
    """Shadow graph rebuilds should pass authoritative rows to the AGE manager."""

    class Repository:
        def list_blogs(self) -> list[dict[str, object]]:
            return [{"id": 1}]

        def list_edges(self) -> list[dict[str, object]]:
            return [{"id": 7}]

    age_manager = Mock()
    age_manager.status.return_value = {
        "graph_backend": "age",
        "age_enabled": True,
        "age_sync_state": "ready",
        "parity_status": "passing",
        "latest_snapshot_namespace": "legacy",
        "age_graph_name": "heyblog_graph",
        "last_error": None,
    }

    service = GraphService(Repository(), tmp_path, graph_backend="age", age_manager=age_manager)
    payload = service.rebuild_shadow_graph()

    age_manager.sync_shadow_graph.assert_called_once_with([{"id": 1}], [{"id": 7}])
    assert payload["graph_backend"] == "age"
