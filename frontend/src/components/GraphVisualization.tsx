import { useEffect, useMemo, useRef, useState } from "react";
import { Graph } from "@antv/g6";
import type { GraphData, GraphNode } from "../types/graph";

interface GraphVisualizationProps {
  data: GraphData;
  onNodeClick?: (node: GraphNode) => void;
  highlightNodeId?: number;
}

type RendererNode = {
  id: string;
  type: "circle" | "image";
  data: GraphNode;
  style: {
    x?: number;
    y?: number;
    size: number;
    fill?: string;
    stroke?: string;
    lineWidth?: number;
    src?: string;
  };
};

type RendererEdge = {
  id: string;
  source: string;
  target: string;
  style: {
    stroke: string;
    lineWidth: number;
    endArrow: boolean;
  };
};

function resolveOriginFaviconUrl(node: GraphNode): string | undefined {
  if (!node.url) {
    return undefined;
  }
  try {
    return new URL("/favicon.ico", node.url).toString();
  } catch {
    return undefined;
  }
}

function resolveDuckDuckGoIconUrl(node: GraphNode): string | undefined {
  const hostname = node.domain?.trim();
  if (!hostname) {
    return undefined;
  }
  return `https://icons.duckduckgo.com/ip3/${hostname}.ico`;
}

function resolveNodeIconUrl(node: GraphNode): string | undefined {
  const originFaviconUrl = resolveOriginFaviconUrl(node);
  const normalizedIconUrl = node.iconUrl?.trim() || undefined;

  if (normalizedIconUrl && normalizedIconUrl !== originFaviconUrl) {
    return normalizedIconUrl;
  }

  const duckDuckGoIconUrl = resolveDuckDuckGoIconUrl(node);
  if (duckDuckGoIconUrl) {
    return duckDuckGoIconUrl;
  }

  if (normalizedIconUrl) {
    return normalizedIconUrl;
  }

  if (originFaviconUrl) {
    return originFaviconUrl;
  }

  if (node.iconUrl) {
    return node.iconUrl;
  }
  return undefined;
}

function buildNodeStyle(node: GraphNode, highlightNodeId?: number) {
  const isHighlighted = node.id === highlightNodeId;
  const iconUrl = resolveNodeIconUrl(node);
  const size = isHighlighted ? 34 : 26;

  if (iconUrl) {
    return {
      x: node.x,
      y: node.y,
      size,
      src: iconUrl,
      lineWidth: isHighlighted ? 3 : 1.5,
    };
  }

  return {
    x: node.x,
    y: node.y,
    size,
    fill: isHighlighted ? "#3b82f6" : "#60a5fa",
    stroke: isHighlighted ? "#1d4ed8" : "#2563eb",
    lineWidth: isHighlighted ? 3 : 1.5,
  };
}

function buildRendererNodes(data: GraphData, highlightNodeId?: number): RendererNode[] {
  return data.nodes.map((node) => {
    const style = buildNodeStyle(node, highlightNodeId);
    return {
      id: String(node.id),
      type: style.src ? "image" : "circle",
      data: node,
      style,
    };
  });
}

function buildRendererEdges(data: GraphData): RendererEdge[] {
  return data.edges.map((edge) => ({
    // G6 requires globally unique element ids across nodes and edges.
    // Backend edge ids are numeric and can collide with node ids, so we namespace them here.
    id: `edge:${edge.id}`,
    source: String(edge.source),
    target: String(edge.target),
    style: {
      stroke: "#94a3b8",
      lineWidth: 1.5,
      endArrow: true,
    },
  }));
}

function buildLayout() {
  return {
    type: "d3-force" as const,
    animation: true,
    nodeSize: 24,
    link: {
      distance: 140,
      strength: 0.2,
    },
    manyBody: {
      strength: -220,
    },
    collide: {
      radius: 28,
      strength: 0.8,
    },
    center: {
      strength: 0.08,
    },
    alpha: 0.9,
    alphaMin: 0.002,
    alphaDecay: 0.04,
    velocityDecay: 0.3,
  };
}

function buildBehaviors() {
  return [
    "drag-canvas",
    "zoom-canvas",
    {
      type: "drag-element-force",
      fixed: false,
    },
  ];
}

/**
 * Render the graph canvas with AntV G6.
 *
 * @param data Graph payload normalized from backend APIs.
 * @param onNodeClick Optional callback for node selection.
 * @param highlightNodeId Selected node id.
 * @returns Graph container.
 */
export function GraphVisualization({ data, onNodeClick, highlightNodeId }: GraphVisualizationProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const latestDataRef = useRef(data);
  const latestOnNodeClickRef = useRef(onNodeClick);
  const [size, setSize] = useState({ width: 960, height: 720 });
  const [renderError, setRenderError] = useState<string | null>(null);

  const rendererEdges = useMemo(() => buildRendererEdges(data), [data]);
  const styledRendererNodes = useMemo(() => buildRendererNodes(data, highlightNodeId), [data, highlightNodeId]);
  const layout = useMemo(() => buildLayout(), []);
  const behaviors = useMemo(() => buildBehaviors(), []);

  useEffect(() => {
    latestDataRef.current = data;
    latestOnNodeClickRef.current = onNodeClick;
  }, [data, onNodeClick]);

  useEffect(() => {
    if (!containerRef.current) {
      return undefined;
    }
    const observer = new ResizeObserver(([entry]) => {
      setSize({
        width: Math.max(640, Math.floor(entry.contentRect.width)),
        height: Math.max(480, Math.floor(entry.contentRect.height)),
      });
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!containerRef.current || graphRef.current) {
      return undefined;
    }

    const graph = new Graph({
      container: containerRef.current,
      width: size.width,
      height: size.height,
      autoFit: "view",
      data: {
        nodes: [],
        edges: [],
      } as never,
      edge: {
        type: "line",
      },
    });

    graph.on("node:click", (event: any) => {
      const targetId = Number(event?.target?.id);
      const node = latestDataRef.current.nodes.find((item) => item.id === targetId);
      if (node) {
        latestOnNodeClickRef.current?.(node);
      }
    });

    graphRef.current = graph;

    return () => {
      graphRef.current = null;
      graph.destroy();
    };
  }, [size.height, size.width]);

  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) {
      return;
    }
    let cancelled = false;

    const renderGraph = async () => {
      try {
        graph.setSize(size.width, size.height);
        graph.setOptions({
          autoFit: "view",
          data: {
            nodes: styledRendererNodes,
            edges: rendererEdges,
          } as never,
          behaviors,
          layout,
        });
        await graph.render();
        if (!cancelled) {
          setRenderError(null);
        }
      } catch (error) {
        console.error("graph_render_failed", error);
        if (!cancelled) {
          setRenderError("图谱渲染失败，请刷新页面重试");
        }
      }
    };

    void renderGraph();

    return () => {
      cancelled = true;
    };
  }, [behaviors, layout, rendererEdges, size.height, size.width, styledRendererNodes]);

  return (
    <div className="relative h-full w-full bg-gradient-to-br from-blue-50 to-indigo-50">
      <div ref={containerRef} className="h-full w-full" />
      {renderError ? (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-white/70 px-6 text-center text-sm text-red-700">
          {renderError}
        </div>
      ) : null}
    </div>
  );
}
