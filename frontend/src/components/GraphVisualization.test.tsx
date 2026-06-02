import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { GraphVisualization } from "./GraphVisualization";
import { tuneNaturalClusterForces } from "./GraphVisualization";
import type { ForwardedRef } from "react";
import type { GraphData } from "../types/graph";

const { chargeForce, d3ReheatSimulation, forceCalls, forceGraphRenders, ForceGraph3DMock, linkForce } = vi.hoisted(
  () => {
    const forceGraphRenders: Record<string, any>[] = [];
    const forceCalls: Array<[string, unknown?]> = [];
    const chargeForce = {
      strength: vi.fn(),
      distanceMax: vi.fn(),
    };
    const linkForce = {
      strength: vi.fn(),
      distance: vi.fn(),
    };
    const d3ReheatSimulation = vi.fn();

    function ForceGraph3DMock(props: Record<string, any>, ref: ForwardedRef<Record<string, unknown>>) {
      forceGraphRenders.push(props);
      const { onNodeClick, graphData } = props;
      const resolvedRef = ref ?? props.ref;
      if (resolvedRef) {
        const graphInstance = {
          d3Force: vi.fn((name: string, force?: unknown) => {
            forceCalls.push([name, force]);
            if (name === "charge") {
              return chargeForce;
            }
            if (name === "link") {
              return linkForce;
            }
            return undefined;
          }),
          d3ReheatSimulation,
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
        if (typeof resolvedRef === "function") {
          resolvedRef(graphInstance);
        } else {
          resolvedRef.current = graphInstance;
        }
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

    return { chargeForce, d3ReheatSimulation, forceCalls, forceGraphRenders, ForceGraph3DMock, linkForce };
  },
);

vi.mock("react-force-graph-3d", async () => {
  const React = await vi.importActual<typeof import("react")>("react");
  return {
    default: React.forwardRef(ForceGraph3DMock),
  };
});

vi.mock("three", async () => {
  const actual = await vi.importActual<typeof import("three")>("three");
  return {
    ...actual,
    TextureLoader: class {
      setCrossOrigin = vi.fn();

      load = vi.fn((url: string, onLoad?: (texture: any) => void) => {
        const texture = new actual.Texture();
        texture.userData = { url };
        onLoad?.(texture);
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
  forceCalls.length = 0;
  chargeForce.strength.mockClear();
  chargeForce.distanceMax.mockClear();
  linkForce.strength.mockClear();
  linkForce.distance.mockClear();
  d3ReheatSimulation.mockClear();
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
              iconUrl: "/api/icons/proxy?url=https%3A%2F%2Falpha.example.com%2Ffavicon.ico",
              val: 1,
            }),
            expect.objectContaining({
              id: "2",
              blogId: 2,
              label: "Beta Blog",
              iconUrl:
                "/api/icons/proxy?url=https%3A%2F%2Ft2.gstatic.com%2FfaviconV2%3Fclient%3DSOCIAL%26type%3DFAVICON%26fallback_opts%3DTYPE%2CSIZE%2CURL%26url%3Dhttps%3A%2F%2Fbeta.example.com%26size%3D64",
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

    expect(graphProps!.linkWidth(selectedLink)).toBe(3.2);
    expect(graphProps!.linkColor(selectedLink)).toBe("rgba(240, 249, 255, 1)");
    expect(graphProps!.linkWidth(unrelatedLink)).toBe(0.9);
    expect(graphProps!.linkColor(unrelatedLink)).toBe("rgba(186, 230, 253, 0.55)");
  });

  test("uses brighter default link color on the dark graph background", () => {
    render(<GraphVisualization data={forceGraphData} />);

    const graphProps = forceGraphRenders.at(-1);
    const [defaultLink] = graphProps!.graphData.links;

    expect(graphProps!.linkWidth(defaultLink)).toBe(1.6);
    expect(graphProps!.linkColor(defaultLink)).toBe("rgba(224, 242, 254, 0.78)");
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
    expect(nodeObject.userData.iconUrl).toBe("/api/icons/proxy?url=https%3A%2F%2Falpha.example.com%2Ffavicon.ico");
  });

  test("tunes forces for natural clusters instead of a centered sphere", () => {
    const graph = {
      d3Force: vi.fn((name: string, force?: unknown) => {
        forceCalls.push([name, force]);
        if (name === "charge") {
          return chargeForce;
        }
        if (name === "link") {
          return linkForce;
        }
        return undefined;
      }),
      d3ReheatSimulation,
    };

    tuneNaturalClusterForces(graph as never);

    expect(forceCalls).toContainEqual(["center", null]);
    expect(chargeForce.strength).toHaveBeenCalledWith(-95);
    expect(chargeForce.distanceMax).toHaveBeenCalledWith(920);
    expect(linkForce.distance).toHaveBeenCalledWith(72);
    expect(linkForce.strength).toHaveBeenCalledWith(0.34);
    expect(d3ReheatSimulation).toHaveBeenCalled();
  });
});
