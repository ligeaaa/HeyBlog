#!/usr/bin/env python3
"""Generate a deterministic clustered graph payload for visualization QA.

The benchmark uses a seeded stochastic-block-model style construction:
blogs are assigned to planted communities, intra-community edges are sampled
with a higher probability than inter-community bridges, and a few hub blogs are
given extra outgoing links. This mirrors the practical idea behind LFR-style
community-detection benchmarks: a known community assignment plus a controllable
mixing rate for cross-community edges.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT = Path("frontend/public/benchmarks/blog-community-graph.json")
DEFAULT_SEED = 42
COMMUNITIES = [
    ("indie-web", "Indie Web", 24),
    ("engineering", "Engineering", 22),
    ("design", "Design", 18),
    ("data-ai", "Data & AI", 20),
    ("culture", "Culture", 16),
]


@dataclass(frozen=True)
class BlogNode:
    """Synthetic blog node emitted in backend-compatible graph JSON form.

    Attributes:
        id: Stable numeric blog id.
        slug: URL-safe blog slug.
        title: Human-readable blog title.
        community_id: Planted benchmark community id.
        community_label: Human-readable community label.
    """

    id: int
    slug: str
    title: str
    community_id: str
    community_label: str


def parse_args() -> argparse.Namespace:
    """Parse command-line options for benchmark graph generation.

    Returns:
        Parsed argparse namespace containing output path, seed, and edge rates.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="JSON output path.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Deterministic random seed.")
    parser.add_argument("--intra-probability", type=float, default=0.34, help="Same-community edge probability.")
    parser.add_argument("--inter-probability", type=float, default=0.002, help="Cross-community edge probability.")
    parser.add_argument("--hub-links", type=int, default=1, help="Extra cross-community links per community hub.")
    return parser.parse_args()


def make_slug(label: str, index: int) -> str:
    """Build a stable blog slug from a community label and ordinal.

    Args:
        label: Human-readable community label.
        index: One-based blog index within that community.

    Returns:
        URL-safe synthetic blog slug.
    """

    return f"{label.lower().replace(' & ', '-').replace(' ', '-')}-{index:02d}"


def build_nodes() -> list[BlogNode]:
    """Create the planted blog communities.

    Returns:
        List of 100 synthetic blog nodes split across five communities.
    """

    nodes: list[BlogNode] = []
    next_id = 1
    for community_id, community_label, size in COMMUNITIES:
        for index in range(1, size + 1):
            slug = make_slug(community_label, index)
            nodes.append(
                BlogNode(
                    id=next_id,
                    slug=slug,
                    title=f"{community_label} Notes {index:02d}",
                    community_id=community_id,
                    community_label=community_label,
                )
            )
            next_id += 1
    return nodes


def edge_key(source: int, target: int) -> tuple[int, int]:
    """Normalize a directed edge pair for duplicate checks.

    Args:
        source: Source blog id.
        target: Target blog id.

    Returns:
        Directed edge identity tuple.
    """

    return (source, target)


def add_edge(edges: dict[tuple[int, int], dict[str, Any]], source: BlogNode, target: BlogNode, link_text: str) -> None:
    """Add one directed edge unless it already exists or is a self-link.

    Args:
        edges: Mutable edge dictionary keyed by directed source/target ids.
        source: Source blog node.
        target: Target blog node.
        link_text: Synthetic friend-link label.
    """

    if source.id == target.id:
        return
    key = edge_key(source.id, target.id)
    if key in edges:
        return
    edges[key] = {
        "from_blog_id": source.id,
        "to_blog_id": target.id,
        "link_text": link_text,
        "link_url_raw": f"https://benchmark.heyblog.local/{target.slug}/",
    }


def build_edges(
    nodes: list[BlogNode],
    rng: random.Random,
    intra_probability: float,
    inter_probability: float,
    hub_links: int,
) -> list[dict[str, Any]]:
    """Sample benchmark edges with strong planted community structure.

    Args:
        nodes: Synthetic blog nodes.
        rng: Seeded random number generator.
        intra_probability: Same-community edge probability.
        inter_probability: Cross-community edge probability.
        hub_links: Extra bridge count added from each community hub.

    Returns:
        Backend-compatible edge dictionaries.
    """

    edges: dict[tuple[int, int], dict[str, Any]] = {}
    by_community: dict[str, list[BlogNode]] = {}
    for node in nodes:
        by_community.setdefault(node.community_id, []).append(node)

    for community_nodes in by_community.values():
        for index, source in enumerate(community_nodes):
            target = community_nodes[(index + 1) % len(community_nodes)]
            add_edge(edges, source, target, "blogroll")

    for source_index, source in enumerate(nodes):
        for target in nodes[source_index + 1 :]:
            probability = intra_probability if source.community_id == target.community_id else inter_probability
            if rng.random() >= probability:
                continue
            if rng.random() < 0.5:
                add_edge(edges, source, target, "friend link")
            else:
                add_edge(edges, target, source, "friend link")

    for community_nodes in by_community.values():
        hub = community_nodes[0]
        outside_nodes = [node for node in nodes if node.community_id != hub.community_id]
        for target in rng.sample(outside_nodes, k=min(hub_links, len(outside_nodes))):
            add_edge(edges, hub, target, "community bridge")

    sorted_edges = sorted(edges.values(), key=lambda edge: (edge["from_blog_id"], edge["to_blog_id"]))
    for index, edge in enumerate(sorted_edges, start=1):
        edge["id"] = f"benchmark-edge-{index:03d}"
    return sorted_edges


def degree_counts(nodes: list[BlogNode], edges: list[dict[str, Any]]) -> dict[int, dict[str, int]]:
    """Calculate directed degree counts for frontend visual weighting.

    Args:
        nodes: Synthetic blog nodes.
        edges: Generated directed edge list.

    Returns:
        Mapping from blog id to incoming/outgoing/total degree counters.
    """

    counts = {node.id: {"incoming": 0, "outgoing": 0, "degree": 0} for node in nodes}
    for edge in edges:
        source = int(edge["from_blog_id"])
        target = int(edge["to_blog_id"])
        counts[source]["outgoing"] += 1
        counts[target]["incoming"] += 1
        counts[source]["degree"] += 1
        counts[target]["degree"] += 1
    return counts


def community_centers() -> dict[str, tuple[float, float, float]]:
    """Return fixed 3D centers that make planted communities visually separate.

    Returns:
        Mapping from community id to deterministic x/y/z layout center.
    """

    return {
        "indie-web": (-520.0, -260.0, 0.0),
        "engineering": (520.0, -260.0, 0.0),
        "design": (-520.0, 300.0, 0.0),
        "data-ai": (520.0, 300.0, 0.0),
        "culture": (0.0, 40.0, 520.0),
    }


def node_position(node: BlogNode, index: int, rng: random.Random) -> dict[str, float]:
    """Place one benchmark node near its planted community center.

    Args:
        node: Synthetic blog node to position.
        index: Zero-based node index used for deterministic angular spread.
        rng: Seeded random number generator for small jitter.

    Returns:
        Mapping containing x, y, and z coordinates.
    """

    center_x, center_y, center_z = community_centers()[node.community_id]
    angle = (index * 2.399963229728653) % 6.283185307179586
    radius = 42.0 + (index % 5) * 15.0 + rng.uniform(-8.0, 8.0)
    z_jitter = rng.uniform(-36.0, 36.0)
    return {
        "x": round(center_x + radius * math.cos(angle), 3),
        "y": round(center_y + radius * math.sin(angle), 3),
        "z": round(center_z + z_jitter, 3),
    }


def to_payload(
    nodes: list[BlogNode],
    edges: list[dict[str, Any]],
    seed: int,
    intra_probability: float,
    inter_probability: float,
) -> dict[str, Any]:
    """Build the backend-compatible benchmark graph payload.

    Args:
        nodes: Synthetic blog nodes.
        edges: Generated directed edge list.
        seed: Random seed used for reproducibility.
        intra_probability: Same-community edge probability.
        inter_probability: Cross-community edge probability.

    Returns:
        JSON-serializable graph payload consumed by the frontend.
    """

    counts = degree_counts(nodes, edges)
    position_rng = random.Random(seed + 1009)
    generated_at = datetime.now(timezone.utc).isoformat()
    graph_nodes = []
    for index, node in enumerate(nodes):
        node_counts = counts[node.id]
        graph_nodes.append(
            {
                "id": node.id,
                "url": f"https://benchmark.heyblog.local/{node.slug}/",
                "domain": f"{node.slug}.benchmark.heyblog.local",
                "title": node.title,
                "icon_url": None,
                "incoming_count": node_counts["incoming"],
                "outgoing_count": node_counts["outgoing"],
                "degree": node_counts["degree"],
                "component_id": node.community_id,
                "benchmark_community_label": node.community_label,
                **node_position(node, index, position_rng),
            }
        )

    return {
        "nodes": graph_nodes,
        "edges": edges,
        "meta": {
            "strategy": "synthetic-community-benchmark",
            "limit": len(nodes),
            "source": "scripts/generate_visualization_benchmark.py",
            "generated_at": generated_at,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "selected_nodes": len(nodes),
            "selected_edges": len(edges),
            "available_nodes": len(nodes),
            "available_edges": len(edges),
            "benchmark": {
                "seed": seed,
                "model": "seeded stochastic block model inspired by LFR mixing-parameter benchmarks",
                "community_sizes": {community_id: size for community_id, _label, size in COMMUNITIES},
                "intra_probability": intra_probability,
                "inter_probability": inter_probability,
                "estimated_mixing_rate": round(inter_probability / (intra_probability + inter_probability), 3),
                "layout": "fixed separated community centers with deterministic jitter",
            },
        },
    }


def main() -> None:
    """Generate the benchmark graph JSON file on disk."""

    args = parse_args()
    rng = random.Random(args.seed)
    nodes = build_nodes()
    edges = build_edges(nodes, rng, args.intra_probability, args.inter_probability, args.hub_links)
    payload = to_payload(nodes, edges, args.seed, args.intra_probability, args.inter_probability)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(nodes)} nodes and {len(edges)} edges to {args.output}")


if __name__ == "__main__":
    main()
