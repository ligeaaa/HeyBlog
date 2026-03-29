import { describe, expect, test } from "vitest";
import { buildCytoscapeGraph } from "./cytoscapeGraph";
import type { GraphPayload } from "../api";

const payload: GraphPayload = {
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
    },
    {
      id: 2,
      url: "https://beta.example",
      normalized_url: "https://beta.example",
      domain: "beta.example",
      status_code: 200,
      crawl_status: "queued",
      friend_links_count: 1,
      depth: 1,
      source_blog_id: 1,
      last_crawled_at: null,
      created_at: "2026-03-29T00:00:00Z",
      updated_at: "2026-03-29T00:00:00Z",
    },
  ],
  edges: [
    {
      id: 11,
      from_blog_id: 1,
      to_blog_id: 2,
      link_url_raw: "https://beta.example",
      link_text: "beta",
      discovered_at: "2026-03-29T00:00:00Z",
    },
  ],
};

describe("buildCytoscapeGraph", () => {
  test("creates stable Cytoscape elements and only includes finished nodes", () => {
    const bundle = buildCytoscapeGraph(payload);

    expect(bundle.elements).toHaveLength(1);
    expect(bundle.detailsById.get("1")?.outgoingCount).toBe(0);
    expect(bundle.detailsById.has("2")).toBe(false);
    expect(bundle.elements[0]).toMatchObject({
      data: {
        id: "1",
        label: "alpha.example",
      },
    });
  });
});
