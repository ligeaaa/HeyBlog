import { describe, expect, test } from "vitest";
import { buildCytoscapeGraph, mergeGraphViewPayload } from "./cytoscapeGraph";
import type { GraphViewPayload } from "../api";

const payload: GraphViewPayload = {
  nodes: [
    {
      id: 1,
      url: "https://alpha.example",
      normalized_url: "https://alpha.example",
      domain: "alpha.example",
      status_code: 200,
      crawl_status: "FINISHED",
      friend_links_count: 3,
      depth: 0,
      source_blog_id: null,
      last_crawled_at: null,
      created_at: "2026-03-29T00:00:00Z",
      updated_at: "2026-03-29T00:00:00Z",
      x: 10,
      y: 20,
      degree: 7,
      incoming_count: 3,
      outgoing_count: 4,
      priority_score: 700,
      component_id: "component-1",
    },
  ],
  edges: [],
  meta: {
    strategy: "degree",
    limit: 180,
    sample_mode: "off",
    sample_value: null,
    sample_seed: 7,
    sampled: false,
    focus_node_id: null,
    hops: null,
    has_stable_positions: true,
    snapshot_version: "v1",
    generated_at: "2026-03-31T00:00:00Z",
    source: "snapshot",
    total_nodes: 1,
    total_edges: 0,
    available_nodes: 1,
    available_edges: 0,
    selected_nodes: 1,
    selected_edges: 0,
    graph_fingerprint: "graph-v1",
  },
};

describe("buildCytoscapeGraph", () => {
  test("uses stable snapshot coordinates and labels important nodes", () => {
    const bundle = buildCytoscapeGraph(payload);

    expect(bundle.hasStablePositions).toBe(true);
    expect(bundle.shouldRunLayout).toBe(false);
    expect(bundle.detailsById.get("1")?.outgoingCount).toBe(4);
    expect(bundle.elements[0]).toMatchObject({
      data: {
        id: "1",
        label: "alpha.example",
      },
      position: {
        x: 10,
        y: 20,
      },
    });
  });

  test("signature changes when the underlying view identity changes", () => {
    const bundle = buildCytoscapeGraph(payload);
    const refocusedBundle = buildCytoscapeGraph({
      ...payload,
      meta: {
        ...payload.meta,
        strategy: "neighborhood",
        focus_node_id: 1,
        hops: 2,
        graph_fingerprint: "graph-v2",
      },
    });

    expect(refocusedBundle.signature).not.toBe(bundle.signature);
  });
});

describe("mergeGraphViewPayload", () => {
  test("deduplicates nodes and edges when expanding neighborhoods", () => {
    const merged = mergeGraphViewPayload(payload, {
      nodes: [
        payload.nodes[0],
        {
          ...payload.nodes[0],
          id: 2,
          domain: "beta.example",
          url: "https://beta.example",
          normalized_url: "https://beta.example",
        },
      ],
      edges: [
        {
          id: 11,
          from_blog_id: 1,
          to_blog_id: 2,
          link_url_raw: "https://beta.example",
          link_text: "beta",
          discovered_at: "2026-03-31T00:00:00Z",
        },
      ],
      meta: {
        ...payload.meta,
        strategy: "neighborhood",
        focus_node_id: 1,
        hops: 1,
        selected_nodes: 2,
        selected_edges: 1,
      },
    });

    expect(merged.nodes).toHaveLength(2);
    expect(merged.edges).toHaveLength(1);
    expect(merged.meta.strategy).toBe("neighborhood");
  });
});
