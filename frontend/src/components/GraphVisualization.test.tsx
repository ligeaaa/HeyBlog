import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { GraphVisualization } from "./GraphVisualization";
import type { GraphData } from "../types/graph";

const { forceGraphRenders, ForceGraph3DMock } = vi.hoisted(() => {
  const forceGraphRenders: Record<string, any>[] = [];

  function ForceGraph3DMock(props: Record<string, any>) {
    forceGraphRenders.push(props);
    const { ref, onNodeClick, graphData } = props;
    if (ref) {
      ref.current = {
        d3Force: vi.fn(() => ({
          strength: vi.fn(),
          distance: vi.fn(),
        })),
        d3ReheatSimulation: vi.fn(),
        zoomToFit: vi.fn(),
        camera: vi.fn(() => ({
          position: {
            clone: () => ({
              normalize: () => ({
                multiplyScalar: () => ({ x: 0, y: 0, z: 360 }),
              }),
            }),
            length: () => 360,
            copy: vi.fn(),
          },
        })),
        controls: vi.fn(() => ({ update: vi.fn() })),
        cameraPosition: vi.fn(),
      };
    }

    return (
      <button
        type="button"
        data-testid="force-graph-3d"
        onClick={() => onNodeClick?.(graphData.nodes[1], new MouseEvent("click"))}
      >
        3D graph
      </button>
    );
  }

  return { forceGraphRenders, ForceGraph3DMock };
});

vi.mock("react-force-graph-3d", () => ({
  default: ForceGraph3DMock,
}));

vi.mock("three", async () => {
  const actual = await vi.importActual<typeof import("three")>("three");
  return {
    ...actual,
    TextureLoader: class {
      setCrossOrigin = vi.fn();

      load = vi.fn((url: string, onLoad?: () => void) => {
        const texture = new actual.Texture();
        texture.userData = { url };
        onLoad?.();
        return texture;
      });
    },
  };
});

const forceGraphData: GraphData = {
  nodes: [
    {
      id: 1,
      url: "https://alpha.example.com/",
      domain: "alpha.example.com",
      title: "Alpha Blog",
      iconUrl: "https://alpha.example.com/favicon.ico",
      incomingCount: 1,
      outgoingCount: 1,
    },
    {
      id: 2,
      url: "https://beta.example.com/",
      domain: "beta.example.com",
      title: "Beta Blog",
      iconUrl: null,
      incomingCount: 1,
      outgoingCount: 0,
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
    {
      id: "missing-target",
      source: 1,
      target: 99,
      linkText: null,
      linkUrlRaw: "https://alpha.example.com/missing",
    },
  ],
  meta: {
    strategy: "degree",
    limit: 120,
    hasStablePositions: false,
  },
};

class TestResizeObserver {
  callback: ResizeObserverCallback;

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }

  observe() {
    this.callback(
      [
        {
          contentRect: { width: 960, height: 720 },
        } as ResizeObserverEntry,
      ],
      this,
    );
  }

  unobserve() {}

  disconnect() {}
}

beforeEach(() => {
  forceGraphRenders.length = 0;
  vi.stubGlobal("ResizeObserver", TestResizeObserver);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("GraphVisualization", () => {
  test("passes cleaned node-link data into the 3D force graph", () => {
    render(<GraphVisualization data={forceGraphData} />);

    const graphProps = forceGraphRenders.at(-1);
    expect(graphProps).toBeDefined();

    expect(graphProps).toEqual(
      expect.objectContaining({
        backgroundColor: "#020617",
        controlType: "orbit",
        graphData: expect.objectContaining({
          nodes: expect.arrayContaining([
            expect.objectContaining({
              id: "1",
              blogId: 1,
              label: "Alpha Blog",
              iconUrl: "https://icons.duckduckgo.com/ip3/alpha.example.com.ico",
              val: 1,
            }),
            expect.objectContaining({
              id: "2",
              blogId: 2,
              label: "Beta Blog",
              iconUrl: "https://icons.duckduckgo.com/ip3/beta.example.com.ico",
              val: 1,
            }),
          ]),
          links: [
            expect.objectContaining({
              id: "1-2",
              source: "1",
              target: "2",
            }),
          ],
        }),
      }),
    );
  });

  test("uses the original graph node for click callbacks", () => {
    const handleNodeClick = vi.fn();
    render(<GraphVisualization data={forceGraphData} onNodeClick={handleNodeClick} />);

    fireEvent.click(screen.getByTestId("force-graph-3d"));

    expect(handleNodeClick).toHaveBeenCalledWith(forceGraphData.nodes[1]);
  });

  test("highlights selected-node links and dims unrelated links", () => {
    const graphWithExtraEdge: GraphData = {
      ...forceGraphData,
      nodes: [
        ...forceGraphData.nodes,
        {
          id: 3,
          url: "https://gamma.example.com/",
          domain: "gamma.example.com",
          title: "Gamma Blog",
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
        {
          id: "2-3",
          source: 2,
          target: 3,
          linkText: null,
          linkUrlRaw: "https://beta.example.com/link",
        },
      ],
    };

    render(<GraphVisualization data={graphWithExtraEdge} highlightNodeId={1} />);

    const graphProps = forceGraphRenders.at(-1);
    const [selectedLink, unrelatedLink] = graphProps!.graphData.links;

    expect(graphProps!.linkWidth(selectedLink)).toBe(2);
    expect(graphProps!.linkColor(selectedLink)).toBe("rgba(125, 211, 252, 0.78)");
    expect(graphProps!.linkWidth(unrelatedLink)).toBe(0.35);
    expect(graphProps!.linkColor(unrelatedLink)).toBe("rgba(71, 85, 105, 0.16)");
  });

  test("exposes icon-only zoom and reset controls", () => {
    render(<GraphVisualization data={forceGraphData} />);

    expect(screen.getByRole("button", { name: "缩小图谱" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重置图谱视角" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "放大图谱" })).toBeInTheDocument();
  });

  test("uses blog icons as sprite textures when available", () => {
    render(<GraphVisualization data={forceGraphData} />);

    const graphProps = forceGraphRenders.at(-1);
    const iconNode = graphProps!.graphData.nodes[0];
    const nodeObject = graphProps!.nodeThreeObject(iconNode);

    expect(nodeObject.children).toHaveLength(3);
    expect(nodeObject.userData.iconUrl).toBe("https://icons.duckduckgo.com/ip3/alpha.example.com.ico");
  });
});
