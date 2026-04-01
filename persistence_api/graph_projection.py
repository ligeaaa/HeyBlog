"""Project raw blog/edge rows into graph views and offline snapshots."""

from __future__ import annotations

import json
import math
import random
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LATEST_SNAPSHOT_MANIFEST = "graph-layout-latest.json"
DEFAULT_CORE_LIMIT = 180
DEFAULT_NEIGHBOR_LIMIT = 120
MAX_CORE_LIMIT = 1000
MAX_NEIGHBOR_LIMIT = 400


def utc_now() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(UTC)


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return utc_now().isoformat()


def snapshot_version(now: datetime | None = None) -> str:
    """Return a sortable snapshot version identifier."""
    resolved = now or utc_now()
    return resolved.strftime("%Y%m%dT%H%M%S%fZ")


def snapshot_filename(version: str) -> str:
    """Return the snapshot filename for one version."""
    return f"graph-layout-{version}.json"


def _json_default_serializer(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=_json_default_serializer)
    tmp_path.replace(path)


def load_snapshot_manifest(export_dir: Path) -> dict[str, Any] | None:
    """Return the latest snapshot manifest when available."""
    path = export_dir / LATEST_SNAPSHOT_MANIFEST
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else None


def load_snapshot_payload(export_dir: Path, version: str) -> dict[str, Any] | None:
    """Return one snapshot payload by version when present."""
    path = export_dir / snapshot_filename(version)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else None


def write_snapshot_files(export_dir: Path, payload: dict[str, Any]) -> dict[str, str]:
    """Persist a versioned snapshot plus the latest manifest."""
    version = str(payload["version"])
    snapshot_path = export_dir / snapshot_filename(version)
    manifest_path = export_dir / LATEST_SNAPSHOT_MANIFEST
    manifest = {
        "version": version,
        "generated_at": payload["generated_at"],
        "source": payload["meta"]["source"],
        "has_stable_positions": payload["meta"]["has_stable_positions"],
        "total_nodes": payload["meta"]["total_nodes"],
        "total_edges": payload["meta"]["total_edges"],
        "available_nodes": payload["meta"]["available_nodes"],
        "available_edges": payload["meta"]["available_edges"],
        "graph_fingerprint": payload["meta"]["graph_fingerprint"],
        "file": snapshot_path.name,
    }
    _write_json_atomic(snapshot_path, payload)
    _write_json_atomic(manifest_path, manifest)
    return {
        "graph_snapshot_manifest": str(manifest_path),
        "graph_snapshot": str(snapshot_path),
    }


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _edge_ids_for_nodes(edges: list[dict[str, Any]], selected_ids: set[int]) -> list[dict[str, Any]]:
    return [
        edge
        for edge in edges
        if int(edge["from_blog_id"]) in selected_ids and int(edge["to_blog_id"]) in selected_ids
    ]


def _sorted_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        nodes,
        key=lambda node: (
            -int(node.get("priority_score") or 0),
            -int(node.get("degree") or 0),
            int(node["id"]),
        ),
    )


def _available_graph(
    blogs: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes = [dict(blog) for blog in blogs if str(blog.get("crawl_status")) == "FINISHED"]
    finished_ids = {int(node["id"]) for node in nodes}
    filtered_edges = [
        dict(edge)
        for edge in edges
        if int(edge["from_blog_id"]) in finished_ids and int(edge["to_blog_id"]) in finished_ids
    ]
    return nodes, filtered_edges


def graph_fingerprint(blogs: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str:
    """Return a stable digest for the current graph source rows."""
    payload = {
        "blogs": [dict(sorted(dict(blog).items())) for blog in blogs],
        "edges": [dict(sorted(dict(edge).items())) for edge in edges],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default_serializer,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _build_adjacency(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> tuple[dict[int, set[int]], dict[int, int], dict[int, int]]:
    adjacency = {int(node["id"]): set() for node in nodes}
    incoming: dict[int, int] = {int(node["id"]): 0 for node in nodes}
    outgoing: dict[int, int] = {int(node["id"]): 0 for node in nodes}
    for edge in edges:
        source = int(edge["from_blog_id"])
        target = int(edge["to_blog_id"])
        if source not in adjacency or target not in adjacency:
            continue
        adjacency[source].add(target)
        adjacency[target].add(source)
        outgoing[source] += 1
        incoming[target] += 1
    return adjacency, incoming, outgoing


def _connected_components(adjacency: dict[int, set[int]]) -> list[list[int]]:
    seen: set[int] = set()
    components: list[list[int]] = []
    for node_id in sorted(adjacency):
        if node_id in seen:
            continue
        stack = [node_id]
        component: list[int] = []
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            component.append(current)
            stack.extend(sorted(adjacency[current] - seen, reverse=True))
        components.append(sorted(component))
    components.sort(key=lambda component: (-len(component), component[0]))
    return components


def _component_center(index: int) -> tuple[float, float]:
    if index == 0:
        return (0.0, 0.0)
    golden_angle = math.pi * (3 - math.sqrt(5))
    distance = 900 * math.sqrt(index)
    angle = index * golden_angle
    return (math.cos(angle) * distance, math.sin(angle) * distance)


def _position_component(
    node_ids: list[int],
    *,
    center_x: float,
    center_y: float,
    score_by_id: dict[int, int],
) -> dict[int, tuple[float, float]]:
    ordered_ids = sorted(node_ids, key=lambda node_id: (-score_by_id[node_id], node_id))
    positions: dict[int, tuple[float, float]] = {}
    if not ordered_ids:
        return positions
    positions[ordered_ids[0]] = (center_x, center_y)
    for ordinal, node_id in enumerate(ordered_ids[1:], start=1):
        ring = 1
        remaining = ordinal - 1
        slots = 6
        while remaining >= slots:
            remaining -= slots
            ring += 1
            slots = ring * 6
        angle = (math.pi * 2 * remaining) / max(slots, 1)
        radius = 120 * ring + min(len(ordered_ids) * 2, 80)
        positions[node_id] = (
            center_x + math.cos(angle) * radius,
            center_y + math.sin(angle) * radius,
        )
    return positions


def build_graph_snapshot_payload(
    blogs: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    version: str | None = None,
    generated_at: str | None = None,
    source: str = "snapshot",
) -> dict[str, Any]:
    """Create a stable-position snapshot payload for graph views."""
    resolved_fingerprint = graph_fingerprint(blogs, edges)
    available_nodes, available_edges = _available_graph(blogs, edges)
    adjacency, incoming, outgoing = _build_adjacency(available_nodes, available_edges)
    components = _connected_components(adjacency)
    component_by_node: dict[int, str] = {}
    score_by_id: dict[int, int] = {}

    for node in available_nodes:
        node_id = int(node["id"])
        degree = incoming[node_id] + outgoing[node_id]
        priority_score = degree * 100 + int(node.get("friend_links_count") or 0) * 10
        node["incoming_count"] = incoming[node_id]
        node["outgoing_count"] = outgoing[node_id]
        node["degree"] = degree
        node["priority_score"] = priority_score
        score_by_id[node_id] = priority_score

    positions: dict[int, tuple[float, float]] = {}
    for index, component in enumerate(components):
        component_id = f"component-{index + 1}"
        for node_id in component:
            component_by_node[node_id] = component_id
        center_x, center_y = _component_center(index)
        positions.update(
            _position_component(
                component,
                center_x=center_x,
                center_y=center_y,
                score_by_id=score_by_id,
            )
        )

    for node in available_nodes:
        node_id = int(node["id"])
        x, y = positions.get(node_id, (0.0, 0.0))
        node["x"] = round(x, 2)
        node["y"] = round(y, 2)
        node["component_id"] = component_by_node.get(node_id, "component-1")

    resolved_generated_at = generated_at or utc_now_iso()
    resolved_version = version or snapshot_version()
    return {
        "version": resolved_version,
        "generated_at": resolved_generated_at,
        "nodes": _sorted_nodes(available_nodes),
        "edges": available_edges,
        "meta": {
            "source": source,
            "has_stable_positions": True,
            "graph_fingerprint": resolved_fingerprint,
            "total_nodes": len(blogs),
            "total_edges": len(edges),
            "available_nodes": len(available_nodes),
            "available_edges": len(available_edges),
        },
    }


def _sample_node_ids(
    nodes: list[dict[str, Any]],
    *,
    sample_mode: str,
    sample_value: float | None,
    sample_seed: int,
) -> set[int]:
    ordered_ids = [int(node["id"]) for node in sorted(nodes, key=lambda item: int(item["id"]))]
    if sample_mode == "off" or not ordered_ids:
        return set(ordered_ids)
    if sample_mode == "count":
        if sample_value is None:
            return set(ordered_ids)
        count = _clamp_int(int(sample_value), 1, len(ordered_ids))
    elif sample_mode == "percent":
        if sample_value is None:
            return set(ordered_ids)
        count = max(1, math.ceil(len(ordered_ids) * (float(sample_value) / 100)))
    else:
        raise ValueError(f"unsupported sample mode: {sample_mode}")
    picker = random.Random(sample_seed)
    return set(picker.sample(ordered_ids, count))


def _selected_nodes_from_ids(
    nodes: list[dict[str, Any]],
    selected_ids: set[int],
) -> list[dict[str, Any]]:
    return [dict(node) for node in nodes if int(node["id"]) in selected_ids]


def _build_view_payload(
    snapshot: dict[str, Any],
    selected_ids: set[int],
    *,
    strategy: str,
    limit: int,
    sample_mode: str,
    sample_value: float | None,
    sample_seed: int,
    focus_node_id: int | None = None,
    hops: int | None = None,
) -> dict[str, Any]:
    nodes = snapshot["nodes"]
    edges = snapshot["edges"]
    selected_nodes = _sorted_nodes(_selected_nodes_from_ids(nodes, selected_ids))
    selected_edges = _edge_ids_for_nodes(edges, selected_ids)
    return {
        "nodes": selected_nodes,
        "edges": selected_edges,
        "meta": {
            "strategy": strategy,
            "limit": limit,
            "sample_mode": sample_mode,
            "sample_value": sample_value,
            "sample_seed": sample_seed,
            "sampled": sample_mode != "off",
            "focus_node_id": focus_node_id,
            "hops": hops,
            "has_stable_positions": bool(snapshot["meta"].get("has_stable_positions")),
            "snapshot_version": snapshot["version"],
            "generated_at": snapshot["generated_at"],
            "source": snapshot["meta"].get("source", "snapshot"),
            "total_nodes": snapshot["meta"]["total_nodes"],
            "total_edges": snapshot["meta"]["total_edges"],
            "available_nodes": snapshot["meta"]["available_nodes"],
            "available_edges": snapshot["meta"]["available_edges"],
            "selected_nodes": len(selected_nodes),
            "selected_edges": len(selected_edges),
        },
    }


def build_core_graph_view(
    snapshot: dict[str, Any],
    *,
    strategy: str = "degree",
    limit: int = DEFAULT_CORE_LIMIT,
    sample_mode: str = "off",
    sample_value: float | None = None,
    sample_seed: int = 7,
) -> dict[str, Any]:
    """Return the default structured subgraph view."""
    nodes = snapshot["nodes"]
    edges = snapshot["edges"]
    limit = _clamp_int(limit, 24, MAX_CORE_LIMIT)
    sampled_ids = _sample_node_ids(
        nodes,
        sample_mode=sample_mode,
        sample_value=sample_value,
        sample_seed=sample_seed,
    )
    if sample_mode != "off":
        selected_ids = set(sorted(sampled_ids)[:limit])
        return _build_view_payload(
            snapshot,
            selected_ids,
            strategy="random",
            limit=limit,
            sample_mode=sample_mode,
            sample_value=sample_value,
            sample_seed=sample_seed,
        )

    filtered_nodes = [node for node in nodes if int(node["id"]) in sampled_ids]
    node_by_id = {int(node["id"]): node for node in filtered_nodes}
    adjacency, _, _ = _build_adjacency(filtered_nodes, edges)
    ordered_nodes = _sorted_nodes(filtered_nodes)
    if strategy == "seed":
        seed_nodes = [node for node in ordered_nodes if node.get("source_blog_id") is None]
        if not seed_nodes:
            seed_nodes = ordered_nodes[: min(len(ordered_nodes), 18)]
    else:
        strategy = "degree"
        seed_nodes = ordered_nodes[: min(len(ordered_nodes), max(12, limit // 4))]

    selected_ids = {int(node["id"]) for node in seed_nodes[:limit]}
    while len(selected_ids) < limit:
        frontier = sorted(
            {
                neighbor
                for node_id in selected_ids
                for neighbor in adjacency.get(node_id, set())
                if neighbor not in selected_ids
            },
            key=lambda node_id: (
                -int(node_by_id[node_id]["priority_score"]),
                node_id,
            ),
        )
        if not frontier:
            break
        for node_id in frontier:
            selected_ids.add(node_id)
            if len(selected_ids) >= limit:
                break
    if len(selected_ids) < limit:
        for node in ordered_nodes:
            selected_ids.add(int(node["id"]))
            if len(selected_ids) >= limit:
                break
    return _build_view_payload(
        snapshot,
        selected_ids,
        strategy=strategy,
        limit=limit,
        sample_mode=sample_mode,
        sample_value=sample_value,
        sample_seed=sample_seed,
    )


def build_neighborhood_graph_view(
    snapshot: dict[str, Any],
    *,
    node_id: int,
    hops: int = 1,
    limit: int = DEFAULT_NEIGHBOR_LIMIT,
) -> dict[str, Any]:
    """Return the neighborhood expansion around one node."""
    nodes = snapshot["nodes"]
    edges = snapshot["edges"]
    node_map = {int(node["id"]): node for node in nodes}
    if node_id not in node_map:
        raise KeyError(node_id)
    hops = _clamp_int(hops, 1, 2)
    limit = _clamp_int(limit, 12, MAX_NEIGHBOR_LIMIT)
    adjacency, _, _ = _build_adjacency(nodes, edges)
    distances = {node_id: 0}
    queue = [node_id]
    for current in queue:
        if distances[current] >= hops:
            continue
        for neighbor in sorted(adjacency.get(current, set())):
            if neighbor in distances:
                continue
            distances[neighbor] = distances[current] + 1
            queue.append(neighbor)

    ranked_ids = sorted(
        distances,
        key=lambda current: (
            distances[current],
            -int(node_map[current].get("priority_score") or 0),
            current,
        ),
    )
    selected_ids = set(ranked_ids[:limit])
    return _build_view_payload(
        snapshot,
        selected_ids,
        strategy="neighborhood",
        limit=limit,
        sample_mode="off",
        sample_value=None,
        sample_seed=0,
        focus_node_id=node_id,
        hops=hops,
    )
