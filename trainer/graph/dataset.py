"""Build graph node classification datasets from exported HeyBlog graph files."""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np
from scipy import sparse
from sklearn.feature_extraction import DictVectorizer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split

from crawler.crawling.normalization import normalize_url
from trainer.dataset.schema import SupervisedSample
from trainer.features.assemble import build_structured_feature_rows


POSITIVE_LABELS = {"blog"}
NEGATIVE_LABELS = {"company", "others", "other", "unknown"}


@dataclass(slots=True)
class GraphDataset:
    """In-memory graph classification dataset.

    Args:
        node_ids: Graph node business ids aligned to feature rows.
        urls: Node URLs aligned to feature rows.
        titles: Node titles aligned to feature rows.
        normalized_urls: Normalized URLs aligned to feature rows.
        features: Sparse node feature matrix.
        adjacency: Symmetric normalized sparse adjacency with self-loops.
        labels: Dense labels where ``1`` means blog, ``0`` means non-blog, and ``-1`` means unlabeled.
        split_masks: Boolean masks keyed by ``train``, ``val``, and ``test``.
        labeled_indices: Indices with supervised labels.
        metadata: Serializable dataset summary.
    """

    node_ids: list[int]
    urls: list[str]
    titles: list[str]
    normalized_urls: list[str]
    features: sparse.csr_matrix
    adjacency: sparse.coo_matrix
    labels: np.ndarray
    split_masks: dict[str, np.ndarray]
    labeled_indices: np.ndarray
    metadata: dict[str, Any]


def _normalized_url_value(url: str) -> str:
    value = normalize_url(url)
    return getattr(value, "normalized_url", str(value))


def _domain_from_url(url: str) -> str:
    return urlparse(url).netloc.lower()


def _load_graph(graph_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payload = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("graph.json must contain list-valued 'nodes' and 'edges'")
    return nodes, edges


def _load_binary_labels(labels_path: Path) -> tuple[dict[str, int], dict[str, list[str]], Counter[str]]:
    labels_by_url: dict[str, set[int]] = {}
    raw_labels_by_url: dict[str, list[str]] = {}
    raw_counts: Counter[str] = Counter()
    with labels_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            url = _normalized_url_value(row.get("url") or "")
            label = (row.get("label") or "").strip().lower()
            raw_counts[label] += 1
            raw_labels_by_url.setdefault(url, []).append(label)
            if label in POSITIVE_LABELS:
                labels_by_url.setdefault(url, set()).add(1)
            elif label in NEGATIVE_LABELS:
                labels_by_url.setdefault(url, set()).add(0)

    resolved: dict[str, int] = {}
    for url, values in labels_by_url.items():
        if len(values) == 1:
            resolved[url] = next(iter(values))
    return resolved, raw_labels_by_url, raw_counts


def _node_key(node: dict[str, Any]) -> int:
    value = node.get("blog_id") or node.get("id")
    if value is None:
        raise ValueError(f"graph node missing blog_id/id: {node}")
    return int(value)


def _edge_endpoints(edge: dict[str, Any]) -> tuple[int, int]:
    return int(edge["from_blog_id"]), int(edge["to_blog_id"])


def _node_text(node: dict[str, Any]) -> str:
    """Build a compact text field from graph node metadata.

    Args:
        node: Raw graph node payload.

    Returns:
        Text combining URL, domain, title, identity, and crawl metadata.
    """

    url = str(node.get("normalized_url") or node.get("url") or "")
    title = str(node.get("title") or "")
    domain = str(node.get("domain") or _domain_from_url(url))
    identity_codes = " ".join(str(value) for value in node.get("identity_reason_codes") or [])
    crawl_status = str(node.get("crawl_status") or "")
    return f"url {url} domain {domain} title {title} identity {identity_codes} status {crawl_status}"


def _build_text_features(nodes: list[dict[str, Any]], *, max_features: int) -> sparse.csr_matrix:
    """Build sparse URL/title/metadata character TF-IDF node features."""

    documents = [_node_text(node) for node in nodes]
    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        max_features=max_features,
        min_df=1,
        dtype=np.float32,
    )
    return vectorizer.fit_transform(documents).tocsr()


def _safe_float(value: Any) -> float:
    """Convert graph payload values to finite floats for structured features."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _build_graph_stat_rows(
    *,
    nodes: list[dict[str, Any]],
    in_degree_by_id: dict[int, int],
    out_degree_by_id: dict[int, int],
) -> list[dict[str, float]]:
    """Build graph metadata and degree features for each node."""

    rows: list[dict[str, float]] = []
    for node in nodes:
        node_id = _node_key(node)
        incoming = float(in_degree_by_id.get(node_id, 0))
        outgoing = float(out_degree_by_id.get(node_id, 0))
        persisted_incoming = _safe_float(node.get("incoming_count"))
        persisted_outgoing = _safe_float(node.get("outgoing_count"))
        friend_links = _safe_float(node.get("friend_links_count"))
        connection_count = _safe_float(node.get("connection_count"))
        rows.append(
            {
                "graph:in_degree": incoming,
                "graph:out_degree": outgoing,
                "graph:total_degree": incoming + outgoing,
                "graph:has_incoming": 1.0 if incoming > 0 else 0.0,
                "graph:has_outgoing": 1.0 if outgoing > 0 else 0.0,
                "graph:reciprocity_proxy": min(incoming, outgoing) / max(incoming, outgoing, 1.0),
                "graph:persisted_incoming_count": persisted_incoming,
                "graph:persisted_outgoing_count": persisted_outgoing,
                "graph:friend_links_count": friend_links,
                "graph:connection_count": connection_count,
                "graph:identity_complete": 1.0 if bool(node.get("identity_complete")) else 0.0,
                "graph:has_icon": 1.0 if node.get("icon_url") else 0.0,
                "graph:status_code_ok": 1.0 if int(_safe_float(node.get("status_code"))) == 200 else 0.0,
            }
        )
    return rows


def _nodes_to_supervised_like_samples(nodes: list[dict[str, Any]]) -> list[SupervisedSample]:
    """Convert graph nodes into trainer sample objects for shared features."""

    samples: list[SupervisedSample] = []
    for node in nodes:
        url = str(node.get("url") or node.get("normalized_url") or "")
        normalized_url = _normalized_url_value(str(node.get("normalized_url") or url))
        title = str(node.get("title") or "")
        samples.append(
            SupervisedSample(
                sample_id=normalized_url,
                url=url,
                normalized_url=normalized_url,
                domain=str(node.get("domain") or _domain_from_url(normalized_url)),
                title=title,
                text=_node_text(node),
                raw_labels=[],
                binary_label="non_blog",
                resolution_status="graph_inference",
                resolution_reason="graph_node_features",
                title_missing=not bool(title),
            )
        )
    return samples


def _degree_counts(node_ids: list[int], edges: list[dict[str, Any]]) -> tuple[dict[int, int], dict[int, int]]:
    """Count incoming and outgoing graph edges for each known node id."""

    known = set(node_ids)
    in_degree: dict[int, int] = {node_id: 0 for node_id in node_ids}
    out_degree: dict[int, int] = {node_id: 0 for node_id in node_ids}
    for edge in edges:
        source, target = _edge_endpoints(edge)
        if source in known and target in known:
            out_degree[source] += 1
            in_degree[target] += 1
    return in_degree, out_degree


def _build_node_features(
    *,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    node_ids: list[int],
    max_features: int,
) -> sparse.csr_matrix:
    """Build fused graph node features from text, page semantics, and topology."""

    text_features = _build_text_features(nodes, max_features=max_features)
    in_degree, out_degree = _degree_counts(node_ids, edges)
    structured_rows = build_structured_feature_rows(_nodes_to_supervised_like_samples(nodes))
    graph_rows = _build_graph_stat_rows(nodes=nodes, in_degree_by_id=in_degree, out_degree_by_id=out_degree)
    fused_rows = []
    for structured, graph_stats in zip(structured_rows, graph_rows, strict=True):
        structured.update(graph_stats)
        fused_rows.append(structured)
    structured_features = DictVectorizer(sparse=True).fit_transform(fused_rows).astype(np.float32)
    return sparse.hstack([text_features, structured_features], format="csr", dtype=np.float32)


def _filter_edges_for_mode(
    edges: list[dict[str, Any]],
    *,
    mode: str,
    edge_dropout: float,
    seed: int,
) -> list[dict[str, Any]]:
    """Select graph edges according to one ablation mode.

    Args:
        edges: Raw graph edges from the export.
        mode: ``full`` keeps all edges, ``self_loop`` removes all message
            passing edges, and ``dropout`` keeps a deterministic subset.
        edge_dropout: Fraction of edges to drop in ``dropout`` mode.
        seed: Random seed used for deterministic edge dropout.

    Returns:
        Edge list used for adjacency construction.
    """

    if mode == "full":
        return edges
    if mode == "self_loop":
        return []
    if mode != "dropout":
        raise ValueError(f"Unsupported graph ablation mode: {mode}")
    if edge_dropout <= 0:
        return edges
    if edge_dropout >= 1:
        return []
    rng = np.random.default_rng(seed)
    keep_mask = rng.random(len(edges)) >= edge_dropout
    return [edge for edge, keep in zip(edges, keep_mask, strict=True) if bool(keep)]


def _build_normalized_adjacency(
    *,
    node_ids: list[int],
    edges: list[dict[str, Any]],
) -> sparse.coo_matrix:
    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    rows: list[int] = []
    cols: list[int] = []
    for edge in edges:
        source, target = _edge_endpoints(edge)
        if source not in node_index or target not in node_index:
            continue
        source_index = node_index[source]
        target_index = node_index[target]
        rows.extend([source_index, target_index])
        cols.extend([target_index, source_index])
    node_count = len(node_ids)
    rows.extend(range(node_count))
    cols.extend(range(node_count))
    values = np.ones(len(rows), dtype=np.float32)
    adjacency = sparse.coo_matrix((values, (rows, cols)), shape=(node_count, node_count), dtype=np.float32)
    adjacency.sum_duplicates()
    degrees = np.asarray(adjacency.sum(axis=1)).reshape(-1)
    inv_sqrt = np.power(np.maximum(degrees, 1.0), -0.5).astype(np.float32)
    normalized_values = adjacency.data * inv_sqrt[adjacency.row] * inv_sqrt[adjacency.col]
    return sparse.coo_matrix((normalized_values, (adjacency.row, adjacency.col)), shape=adjacency.shape, dtype=np.float32)


def _split_labeled_indices(
    *,
    labeled_indices: np.ndarray,
    labels: np.ndarray,
    seed: int,
    val_ratio: float,
    test_ratio: float,
) -> dict[str, np.ndarray]:
    labeled_y = labels[labeled_indices]
    test_size = val_ratio + test_ratio
    train_indices, holdout_indices, _, holdout_y = train_test_split(
        labeled_indices,
        labeled_y,
        test_size=test_size,
        random_state=seed,
        stratify=labeled_y,
    )
    relative_test = test_ratio / test_size
    val_indices, test_indices = train_test_split(
        holdout_indices,
        test_size=relative_test,
        random_state=seed,
        stratify=holdout_y,
    )
    masks = {}
    for name, indices in {"train": train_indices, "val": val_indices, "test": test_indices}.items():
        mask = np.zeros(labels.shape[0], dtype=bool)
        mask[indices] = True
        masks[name] = mask
    return masks


def load_graph_dataset(
    *,
    dataset_dir: Path,
    max_features: int = 4096,
    seed: int = 7,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    graph_mode: str = "full",
    edge_dropout: float = 0.0,
) -> GraphDataset:
    """Load graph export files and build a supervised graph dataset.

    Args:
        dataset_dir: Directory containing ``graph.json`` and ``labels.csv``.
        max_features: Maximum TF-IDF feature count.
        seed: Random seed for stratified train/val/test splitting.
        val_ratio: Fraction of labeled nodes assigned to validation.
        test_ratio: Fraction of labeled nodes assigned to test.
        graph_mode: Graph ablation mode: ``full``, ``self_loop``, or ``dropout``.
        edge_dropout: Fraction of raw graph edges dropped when
            ``graph_mode='dropout'``.

    Returns:
        A ``GraphDataset`` ready for GCN training and evaluation.

    Raises:
        ValueError: If the graph export is malformed or too few labels overlap the graph.
    """
    graph_path = dataset_dir / "graph.json"
    labels_path = dataset_dir / "labels.csv"
    nodes, edges = _load_graph(graph_path)
    adjacency_edges = _filter_edges_for_mode(edges, mode=graph_mode, edge_dropout=edge_dropout, seed=seed)
    label_by_url, raw_labels_by_url, raw_label_counts = _load_binary_labels(labels_path)

    node_ids = [_node_key(node) for node in nodes]
    normalized_urls = [_normalized_url_value(str(node.get("normalized_url") or node.get("url") or "")) for node in nodes]
    urls = [str(node.get("url") or node.get("normalized_url") or "") for node in nodes]
    titles = [str(node.get("title") or "") for node in nodes]
    labels = np.full(len(nodes), -1, dtype=np.int64)
    for index, normalized_url in enumerate(normalized_urls):
        if normalized_url in label_by_url:
            labels[index] = label_by_url[normalized_url]
    labeled_indices = np.flatnonzero(labels >= 0)
    if labeled_indices.size < 10:
        raise ValueError("Too few labeled graph nodes to train a GCN")

    split_masks = _split_labeled_indices(
        labeled_indices=labeled_indices,
        labels=labels,
        seed=seed,
        val_ratio=val_ratio,
        test_ratio=test_ratio,
    )
    features = _build_node_features(nodes=nodes, edges=edges, node_ids=node_ids, max_features=max_features)
    adjacency = _build_normalized_adjacency(node_ids=node_ids, edges=adjacency_edges)
    split_counts = {
        split: dict(Counter(labels[mask].tolist()))
        for split, mask in split_masks.items()
    }
    metadata = {
        "dataset_dir": str(dataset_dir),
        "graph_nodes": len(nodes),
        "graph_edges": len(edges),
        "adjacency_edges": len(adjacency_edges),
        "graph_mode": graph_mode,
        "edge_dropout": edge_dropout,
        "labeled_nodes": int(labeled_indices.size),
        "unlabeled_nodes": int(len(nodes) - labeled_indices.size),
        "label_overlap_ratio": round(float(labeled_indices.size / max(len(nodes), 1)), 6),
        "raw_label_counts": dict(raw_label_counts),
        "resolved_label_counts": {
            "non_blog": int(np.sum(labels == 0)),
            "blog": int(np.sum(labels == 1)),
        },
        "split_counts": split_counts,
        "feature_shape": list(features.shape),
        "feature_sources": ["char_tfidf_url_title_metadata", "structured_url_title_page", "graph_degree_metadata"],
        "raw_labeled_unique_urls": len(raw_labels_by_url),
        "seed": seed,
        "val_ratio": val_ratio,
        "test_ratio": test_ratio,
    }
    return GraphDataset(
        node_ids=node_ids,
        urls=urls,
        titles=titles,
        normalized_urls=normalized_urls,
        features=features,
        adjacency=adjacency,
        labels=labels,
        split_masks=split_masks,
        labeled_indices=labeled_indices,
        metadata=metadata,
    )
