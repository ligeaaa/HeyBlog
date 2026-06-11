import json
from pathlib import Path

from scripts.generate_visualization_benchmark import main


def test_visualization_benchmark_has_planted_communities(tmp_path: Path, monkeypatch) -> None:
    """Generated benchmark should contain 100 clustered blogs and sparse bridges."""

    output = tmp_path / "benchmark.json"
    monkeypatch.setattr(
        "sys.argv",
        ["generate_visualization_benchmark.py", "--output", str(output)],
    )

    main()

    payload = json.loads(output.read_text(encoding="utf-8"))
    nodes = payload["nodes"]
    edges = payload["edges"]
    community_by_id = {node["id"]: node["component_id"] for node in nodes}
    internal_edges = [
        edge
        for edge in edges
        if community_by_id[edge["from_blog_id"]] == community_by_id[edge["to_blog_id"]]
    ]
    bridge_edges = [edge for edge in edges if edge not in internal_edges]

    assert len(nodes) == 100
    assert 420 <= len(edges) <= 560
    assert len(internal_edges) > len(bridge_edges) * 12
    assert len(bridge_edges) <= 35
    assert payload["meta"]["benchmark"]["seed"] == 42
    assert all({"x", "y", "z"}.issubset(node) for node in nodes)
