import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { D3GraphCanvas } from "./D3GraphCanvas";
import { buildGraphScene } from "../../lib/graph/graphScene";
import type { GraphRendererHandle } from "../../lib/graph/graphRenderer";
import type { GraphViewPayload } from "../../lib/api";
import * as d3GraphRenderer from "../../lib/graph/d3GraphRenderer";

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
      x: 120,
      y: 160,
      degree: 6,
      incoming_count: 2,
      outgoing_count: 4,
      connection_count: 6,
      activity_at: "2026-03-29T00:00:00Z",
      identity_complete: true,
      priority_score: 700,
      component_id: "component-1",
    },
    {
      id: 2,
      url: "https://beta.example",
      normalized_url: "https://beta.example",
      domain: "beta.example",
      title: "Beta Blog",
      icon_url: null,
      status_code: 200,
      crawl_status: "FINISHED",
      friend_links_count: 1,
      last_crawled_at: null,
      created_at: "2026-03-31T00:00:00Z",
      updated_at: "2026-03-31T00:00:00Z",
      x: 260,
      y: 220,
      degree: 1,
      incoming_count: 1,
      outgoing_count: 0,
      connection_count: 1,
      activity_at: "2026-03-31T00:00:00Z",
      identity_complete: false,
      priority_score: 110,
      component_id: "component-1",
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
    total_nodes: 2,
    total_edges: 1,
    available_nodes: 2,
    available_edges: 1,
    selected_nodes: 2,
    selected_edges: 1,
    graph_fingerprint: "graph-v1",
  },
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("D3GraphCanvas", () => {
  test("renders nodes, links, and labels", () => {
    render(
      <D3GraphCanvas
        scene={buildGraphScene(payload)}
        selectedNodeId={null}
        onSelect={() => undefined}
        onViewportChange={() => undefined}
        onOverlayChange={() => undefined}
      />,
    );

    expect(screen.getByTestId("graph-canvas")).toBeInTheDocument();
    expect(document.querySelectorAll(".graph-link")).toHaveLength(1);
    expect(document.querySelectorAll(".graph-node-circle")).toHaveLength(2);
    expect(document.querySelectorAll(".graph-node-icon")).toHaveLength(2);
    expect(document.querySelector("image.graph-node-icon")?.getAttribute("display")).not.toBe("none");
    expect(screen.getByText("Alpha Blog")).toBeInTheDocument();
  });

  test("clicking the background clears selection", async () => {
    const onSelect = vi.fn();

    render(
      <D3GraphCanvas
        scene={buildGraphScene(payload)}
        selectedNodeId="1"
        onSelect={onSelect}
        onViewportChange={() => undefined}
        onOverlayChange={() => undefined}
      />,
    );

    fireEvent.click(screen.getByTestId("graph-canvas"));

    expect(onSelect).toHaveBeenCalledWith(null);
  });

  test("imperative controller methods stay callable", () => {
    const ref = createRef<GraphRendererHandle>();
    const onViewportChange = vi.fn();

    render(
      <D3GraphCanvas
        ref={ref}
        scene={buildGraphScene(payload)}
        selectedNodeId={null}
        onSelect={() => undefined}
        onViewportChange={onViewportChange}
        onOverlayChange={() => undefined}
      />,
    );

    ref.current?.fitView();
    const snapshot = ref.current?.captureViewport();
    ref.current?.restoreViewport({ x: 10, y: 20, k: 1.2 });
    ref.current?.requestRelayout("soft");
    ref.current?.clearSelection();

    expect(snapshot).toEqual(expect.objectContaining({ x: expect.any(Number), y: expect.any(Number), k: expect.any(Number) }));
    expect(onViewportChange).toHaveBeenCalled();
  });

  test("selection changes do not collapse edge rendering", () => {
    const { rerender } = render(
      <D3GraphCanvas
        scene={buildGraphScene(payload)}
        selectedNodeId={null}
        onSelect={() => undefined}
        onViewportChange={() => undefined}
        onOverlayChange={() => undefined}
      />,
    );

    rerender(
      <D3GraphCanvas
        scene={buildGraphScene(payload)}
        selectedNodeId="1"
        onSelect={() => undefined}
        onViewportChange={() => undefined}
        onOverlayChange={() => undefined}
      />,
    );

    const edge = document.querySelector(".graph-link");
    expect(edge?.getAttribute("x1")).not.toBe("0");
    expect(edge?.getAttribute("x2")).not.toBe("0");
  });

  test("keyboard activation selects a focused node", () => {
    const onSelect = vi.fn();

    render(
      <D3GraphCanvas
        scene={buildGraphScene(payload)}
        selectedNodeId={null}
        onSelect={onSelect}
        onViewportChange={() => undefined}
        onOverlayChange={() => undefined}
      />,
    );

    const firstNode = document.querySelector<SVGGElement>("g.graph-node");
    expect(firstNode).not.toBeNull();

    firstNode?.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));

    expect(onSelect).toHaveBeenCalledWith("1");
  });

  test("relayout emits overlays with the latest scene fingerprint", () => {
    let endHandler: (() => void) | null = null;
    const createGraphSimulationSpy = vi.spyOn(d3GraphRenderer, "createGraphSimulation").mockImplementation(
      () =>
        ({
          stop: vi.fn(),
          on: vi.fn((event: string, handler: () => void) => {
            if (event === "end") {
              endHandler = handler;
            }
            return fakeSimulation;
          }),
          alpha: vi.fn(() => ({
            restart: () => {
              endHandler?.();
              return fakeSimulation;
            },
          })),
          alphaTarget: vi.fn(() => fakeSimulation),
        }) as unknown as ReturnType<typeof d3GraphRenderer.createGraphSimulation>,
    );
    const fakeSimulation = {
      stop: vi.fn(),
      on: vi.fn((event: string, handler: () => void) => {
        if (event === "end") {
          endHandler = handler;
        }
        return fakeSimulation;
      }),
      alpha: vi.fn(() => ({
        restart: () => {
          endHandler?.();
          return fakeSimulation;
        },
      })),
      alphaTarget: vi.fn(() => fakeSimulation),
    };
    const ref = createRef<GraphRendererHandle>();
    const onOverlayChange = vi.fn();
    const { rerender } = render(
      <D3GraphCanvas
        ref={ref}
        scene={buildGraphScene(payload)}
        selectedNodeId={null}
        onSelect={() => undefined}
        onViewportChange={() => undefined}
        onOverlayChange={onOverlayChange}
      />,
    );

    rerender(
      <D3GraphCanvas
        ref={ref}
        scene={buildGraphScene({
          ...payload,
          meta: {
            ...payload.meta,
            graph_fingerprint: "graph-v2",
          },
        })}
        selectedNodeId={null}
        onSelect={() => undefined}
        onViewportChange={() => undefined}
        onOverlayChange={onOverlayChange}
      />,
    );

    ref.current?.requestRelayout("soft");

    expect(createGraphSimulationSpy).toHaveBeenCalled();
    expect(onOverlayChange).toHaveBeenLastCalledWith(
      expect.objectContaining({
        graphFingerprint: "graph-v2",
      }),
    );
  });
});
