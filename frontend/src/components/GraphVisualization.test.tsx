import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { GraphVisualization } from "./GraphVisualization";
import type { GraphData } from "../types/graph";

const { graphInstances, GraphMock } = vi.hoisted(() => {
  const graphInstances: {
    options: Record<string, unknown>;
    setOptions: ReturnType<typeof vi.fn>;
    setSize: ReturnType<typeof vi.fn>;
    updateNodeData: ReturnType<typeof vi.fn>;
    render: ReturnType<typeof vi.fn>;
    draw: ReturnType<typeof vi.fn>;
    destroy: ReturnType<typeof vi.fn>;
    on: ReturnType<typeof vi.fn>;
  }[] = [];

  class GraphMock {
    options: Record<string, unknown>;
    setOptions = vi.fn((nextOptions: Record<string, unknown>) => {
      this.options = { ...this.options, ...nextOptions };
    });
    setSize = vi.fn();
    updateNodeData = vi.fn();
    render = vi.fn(() => Promise.resolve());
    draw = vi.fn(() => Promise.resolve());
    destroy = vi.fn();
    on = vi.fn();

    constructor(options: Record<string, unknown>) {
      this.options = options;
      graphInstances.push(this);
    }
  }

  return { graphInstances, GraphMock };
});

vi.mock("@antv/g6", () => ({
  Graph: GraphMock,
}));

const forceGraphData: GraphData = {
  nodes: [
    {
      id: 1,
      url: "https://alpha.example.com/",
      domain: "alpha.example.com",
      title: "Alpha Blog",
      iconUrl: "https://alpha.example.com/favicon.ico",
    },
    {
      id: 2,
      url: "https://beta.example.com/",
      domain: "beta.example.com",
      title: "Beta Blog",
      iconUrl: null,
    },
  ],
  edges: [
    {
      id: "1-2",
      source: 1,
      target: 2,
      linkText: null,
      linkUrlRaw: "https://alpha.example.com/link",
    },
  ],
  meta: {
    strategy: "degree",
    limit: 120,
    hasStablePositions: false,
  },
};

beforeEach(() => {
  graphInstances.length = 0;
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("GraphVisualization", () => {
  test("uses drag-element-force for d3-force graphs", () => {
    render(<GraphVisualization data={forceGraphData} />);

    expect(graphInstances).toHaveLength(1);
    expect(graphInstances[0].setOptions).toHaveBeenCalledWith(
      expect.objectContaining({
        layout: expect.objectContaining({ type: "d3-force" }),
        behaviors: expect.arrayContaining([
          "drag-canvas",
          "zoom-canvas",
          expect.objectContaining({
            type: "drag-element-force",
            fixed: false,
          }),
        ]),
      }),
    );
    expect(graphInstances[0].setOptions).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          nodes: expect.arrayContaining([
            expect.objectContaining({
              id: "1",
              type: "image",
              style: expect.objectContaining({
                src: "https://icons.duckduckgo.com/ip3/alpha.example.com.ico",
              }),
            }),
            expect.objectContaining({
              id: "2",
              type: "image",
              style: expect.objectContaining({
                src: "https://icons.duckduckgo.com/ip3/beta.example.com.ico",
              }),
            }),
          ]),
        }),
      }),
    );
  });

  test("prefers domain icon service when backend only exposes synthesized /favicon.ico", () => {
    const staleMetadataGraph: GraphData = {
      ...forceGraphData,
      nodes: [
        {
          id: 3,
          url: "https://dusays.com/",
          domain: "dusays.com",
          title: "dusays.com",
          iconUrl: "https://dusays.com/favicon.ico",
        },
      ],
      edges: [],
    };

    render(<GraphVisualization data={staleMetadataGraph} />);

    expect(graphInstances).toHaveLength(1);
    expect(graphInstances[0].setOptions).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          nodes: [
            expect.objectContaining({
              id: "3",
              type: "image",
              style: expect.objectContaining({
                src: "https://icons.duckduckgo.com/ip3/dusays.com.ico",
              }),
            }),
          ],
        }),
      }),
    );
  });

  test("updates highlighted node styles without recreating the graph instance", () => {
    const { rerender } = render(<GraphVisualization data={forceGraphData} />);

    expect(graphInstances).toHaveLength(1);

    rerender(<GraphVisualization data={forceGraphData} highlightNodeId={2} />);

    expect(graphInstances).toHaveLength(1);
    expect(graphInstances[0].destroy).not.toHaveBeenCalled();
    expect(graphInstances[0].setOptions).toHaveBeenCalledTimes(2);
  });

  test("keeps preset graphs on ordinary drag-element behavior", () => {
    const presetGraphData: GraphData = {
      ...forceGraphData,
      meta: {
        strategy: forceGraphData.meta?.strategy ?? "degree",
        limit: forceGraphData.meta?.limit ?? 120,
        hasStablePositions: true,
      },
      nodes: forceGraphData.nodes.map((node, index) => ({
        ...node,
        x: 100 + index * 40,
        y: 200 + index * 40,
      })),
    };

    render(<GraphVisualization data={presetGraphData} />);

    expect(graphInstances).toHaveLength(1);
    expect(graphInstances[0].setOptions).toHaveBeenCalledWith(
      expect.objectContaining({
        layout: expect.objectContaining({ type: "d3-force" }),
        behaviors: expect.arrayContaining([
          "drag-canvas",
          "zoom-canvas",
          expect.objectContaining({
            type: "drag-element-force",
            fixed: false,
          }),
        ]),
      }),
    );
  });
});
