import { describe, expect, test } from "vitest";
import { buildGraphScene, mergeGraphViewPayload, type GraphPositionOverlay } from "./graphScene";
import type { GraphViewPayload } from "../api";

const payload: GraphViewPayload = {
  nodes: [
    {
      id: 1,
      url: "https://alpha.example",
      normalized_url: "https://alpha.example",
      domain: "alpha.example",
      title: "Alpha Blog",
      icon_url: "https://alpha.example/favicon.ico",
      status_code: 200,
      crawl_status: "FINISHED",
      friend_links_count: 3,
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

describe("buildGraphScene", () => {
  test("uses stable snapshot coordinates and captures node details", () => {
    const scene = buildGraphScene(payload);

    expect(scene.hasStablePositions).toBe(true);
    expect(scene.shouldRunLayout).toBe(false);
    expect(scene.detailsById.get("1")?.outgoingCount).toBe(4);
    expect(scene.detailsById.get("1")?.iconUrl).toBe("https://alpha.example/favicon.ico");
    expect(scene.nodes[0]).toMatchObject({
      id: "1",
      label: "Alpha Blog",
      position: { x: 10, y: 20 },
      visual: {
        showLabel: true,
        hasIcon: true,
      },
    });
  });

  test("uses overlay positions only when the fingerprint matches", () => {
    const overlay: GraphPositionOverlay = {
      graphFingerprint: "graph-v1",
      positions: new Map([["1", { x: 210, y: 320 }]]),
    };

    const restoredScene = buildGraphScene(payload, overlay);
    const staleOverlayScene = buildGraphScene(payload, {
      graphFingerprint: "graph-v2",
      positions: overlay.positions,
    });

    expect(restoredScene.nodes[0]?.position).toEqual({ x: 210, y: 320 });
    expect(staleOverlayScene.nodes[0]?.position).toEqual({ x: 10, y: 20 });
  });

  test("falls back to seeded positions when stable coordinates are unavailable", () => {
    const scene = buildGraphScene({
      ...payload,
      nodes: payload.nodes.map((node) => ({
        ...node,
        x: undefined,
        y: undefined,
      })),
      meta: {
        ...payload.meta,
        has_stable_positions: false,
      },
    });

    expect(scene.shouldRunLayout).toBe(true);
    expect(scene.nodes[0]?.position.x).toBeGreaterThan(0);
    expect(scene.nodes[0]?.position.y).toBeGreaterThan(0);
  });

  test("signature changes when the underlying view identity changes", () => {
    const scene = buildGraphScene(payload);
    const refocusedScene = buildGraphScene({
      ...payload,
      meta: {
        ...payload.meta,
        strategy: "neighborhood",
        focus_node_id: 1,
        hops: 2,
        graph_fingerprint: "graph-v2",
      },
    });

    expect(refocusedScene.signature).not.toBe(scene.signature);
  });

  test("raises the label threshold when the scene is large", () => {
    const largeScene = buildGraphScene({
      ...payload,
      nodes: Array.from({ length: 260 }, (_, index) => ({
        ...payload.nodes[0],
        id: index + 1,
        domain: `site-${index + 1}.example`,
        url: `https://site-${index + 1}.example`,
        normalized_url: `https://site-${index + 1}.example`,
        title: `Site ${index + 1}`,
      })),
      meta: {
        ...payload.meta,
        selected_nodes: 260,
      },
    });

    expect(largeScene.performanceMode.reduceLabels).toBe(true);
    expect(largeScene.performanceMode.labelDegreeThreshold).toBeGreaterThan(5);
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
          title: "Beta Blog",
          icon_url: "https://beta.example/favicon.ico",
          url: "https://beta.example",
          normalized_url: "https://beta.example",
          x: 160,
          y: 140,
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
    expect(merged.meta.selected_nodes).toBe(2);
  });
});
