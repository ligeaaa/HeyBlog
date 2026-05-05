import { RotateCcw, ZoomIn, ZoomOut } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ForceGraph3D, { type ForceGraphMethods } from "react-force-graph-3d";
import * as THREE from "three";
import type { GraphData, GraphEdge, GraphNode } from "../types/graph";

interface GraphVisualizationProps {
  data: GraphData;
  onNodeClick?: (node: GraphNode) => void;
  highlightNodeId?: number;
}

interface RenderNode extends Omit<GraphNode, "id" | "iconUrl"> {
  id: string;
  blogId: number;
  original: GraphNode;
  label: string;
  val: number;
  iconUrl?: string;
}

interface RenderLink extends Omit<GraphEdge, "source" | "target"> {
  source: string | RenderNode;
  target: string | RenderNode;
}

interface RenderGraphData {
  nodes: RenderNode[];
  links: RenderLink[];
}

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

  return resolveDuckDuckGoIconUrl(node) ?? normalizedIconUrl ?? originFaviconUrl ?? node.iconUrl ?? undefined;
}

function nodeTitle(node: GraphNode): string {
  return node.title?.trim() || node.domain || node.url || `Blog ${node.id}`;
}

function sourceIdOf(link: RenderLink): string {
  return typeof link.source === "object" ? link.source.id : String(link.source);
}

function targetIdOf(link: RenderLink): string {
  return typeof link.target === "object" ? link.target.id : String(link.target);
}

function buildGraphData(data: GraphData): RenderGraphData {
  const nodesById = new Map<string, RenderNode>();

  for (const node of data.nodes) {
    const id = String(node.id).trim();
    if (!id) {
      continue;
    }
    nodesById.set(id, {
      ...node,
      id,
      blogId: node.id,
      original: node,
      label: nodeTitle(node),
      val: 1,
      iconUrl: resolveNodeIconUrl(node),
    });
  }

  const degreeById = new Map<string, number>();
  const links: RenderLink[] = [];

  for (const edge of data.edges) {
    const source = String(edge.source).trim();
    const target = String(edge.target).trim();
    if (!source || !target || !nodesById.has(source) || !nodesById.has(target)) {
      continue;
    }

    degreeById.set(source, (degreeById.get(source) ?? 0) + 1);
    degreeById.set(target, (degreeById.get(target) ?? 0) + 1);
    links.push({
      ...edge,
      source,
      target,
    });
  }

  const nodes = Array.from(nodesById.values()).map((node) => ({
    ...node,
    val: Math.max(1, degreeById.get(node.id) ?? node.degree ?? 1),
  }));

  return { nodes, links };
}

function buildNeighborIds(graphData: RenderGraphData, highlightNodeId?: number): Set<string> {
  const highlightId = highlightNodeId === undefined ? undefined : String(highlightNodeId);
  const neighborIds = new Set<string>();
  if (!highlightId) {
    return neighborIds;
  }

  for (const link of graphData.links) {
    const source = sourceIdOf(link);
    const target = targetIdOf(link);
    if (source === highlightId) {
      neighborIds.add(target);
    }
    if (target === highlightId) {
      neighborIds.add(source);
    }
  }
  return neighborIds;
}

function colorForNode(node: RenderNode, highlightNodeId?: number, neighborIds?: Set<string>): string {
  const isSelected = node.blogId === highlightNodeId;
  const isNeighbor = neighborIds?.has(node.id) ?? false;
  if (isSelected) {
    return "#38bdf8";
  }
  if (isNeighbor) {
    return "#a7f3d0";
  }
  if (highlightNodeId !== undefined) {
    return "#334155";
  }
  if ((node.incomingCount ?? 0) > (node.outgoingCount ?? 0)) {
    return "#fbbf24";
  }
  if ((node.outgoingCount ?? 0) > 0) {
    return "#818cf8";
  }
  return "#94a3b8";
}

function sizeForNode(node: RenderNode, highlightNodeId?: number): number {
  const baseSize = Math.min(9, 3.5 + Math.sqrt(node.val));
  return node.blogId === highlightNodeId ? baseSize + 2.5 : baseSize;
}

function createNodeObject(node: RenderNode, color: string, size: number): THREE.Object3D {
  const group = new THREE.Group();
  const glow = new THREE.Mesh(
    new THREE.SphereGeometry(size * 1.9, 24, 24),
    new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: 0.18,
      depthWrite: false,
    }),
  );
  const core = new THREE.Mesh(
    new THREE.SphereGeometry(size, 24, 24),
    new THREE.MeshStandardMaterial({
      color,
      emissive: color,
      emissiveIntensity: 0.35,
      roughness: 0.55,
    }),
  );

  group.add(glow);
  group.add(core);

  if (node.iconUrl) {
    const loader = new THREE.TextureLoader();
    loader.setCrossOrigin("anonymous");
    const texture = loader.load(
      node.iconUrl,
      () => {
        core.visible = false;
      },
      undefined,
      () => {
        core.visible = true;
      },
    );
    texture.colorSpace = THREE.SRGBColorSpace;
    const icon = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: texture,
        color: "#ffffff",
        transparent: true,
      }),
    );
    icon.scale.set(size * 2.1, size * 2.1, 1);
    icon.position.set(0, 0, size * 0.08);
    group.add(icon);
  }

  group.userData = { blogId: node.blogId, iconUrl: node.iconUrl };
  return group;
}

/**
 * Render an interactive 3D force graph for blog relationship exploration.
 *
 * @param data Graph payload normalized from backend APIs.
 * @param onNodeClick Optional callback fired with the original graph node.
 * @param highlightNodeId Selected node id to emphasize.
 * @returns Graph container with 3D canvas and controls.
 */
export function GraphVisualization({ data, onNodeClick, highlightNodeId }: GraphVisualizationProps) {
  const graphRef = useRef<ForceGraphMethods<RenderNode, RenderLink> | undefined>(undefined);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: 960, height: 720 });
  const [isMeasured, setIsMeasured] = useState(false);
  const graphData = useMemo(() => buildGraphData(data), [data]);
  const neighborIds = useMemo(() => buildNeighborIds(graphData, highlightNodeId), [graphData, highlightNodeId]);
  const selectedGraphId = highlightNodeId === undefined ? undefined : String(highlightNodeId);

  useEffect(() => {
    if (!containerRef.current) {
      return undefined;
    }

    const observer = new ResizeObserver(([entry]) => {
      setSize({
        width: Math.max(320, Math.floor(entry.contentRect.width)),
        height: Math.max(360, Math.floor(entry.contentRect.height)),
      });
      setIsMeasured(true);
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const graph = graphRef.current;
    if (!graph || !selectedGraphId) {
      return;
    }

    const node = graphData.nodes.find((item) => item.id === selectedGraphId) as
      | (RenderNode & { x?: number; y?: number; z?: number })
      | undefined;
    if (!node || node.x === undefined || node.y === undefined || node.z === undefined) {
      return;
    }

    const distance = 280;
    const ratio = 1 + distance / Math.max(1, Math.hypot(node.x, node.y, node.z));
    graph.cameraPosition(
      { x: node.x * ratio, y: node.y * ratio, z: node.z * ratio },
      { x: node.x, y: node.y, z: node.z },
      800,
    );
  }, [graphData.nodes, selectedGraphId]);

  const handleZoom = useCallback((scale: number) => {
    const graph = graphRef.current;
    if (!graph) {
      return;
    }
    const camera = graph.camera();
    const controls = graph.controls() as { update?: () => void };
    const direction = camera.position.clone().normalize();
    camera.position.copy(direction.multiplyScalar(camera.position.length() * scale));
    controls.update?.();
  }, []);

  const handleResetView = useCallback(() => {
    graphRef.current?.zoomToFit(650, 80);
  }, []);

  return (
    <div ref={containerRef} className="relative h-full w-full overflow-hidden bg-slate-950">
      <div className="absolute inset-x-0 top-0 z-10 h-24 bg-gradient-to-b from-slate-950 via-slate-950/70 to-transparent" />
      {isMeasured ? (
        <ForceGraph3D<RenderNode, RenderLink>
          ref={graphRef}
          graphData={graphData}
          nodeId="id"
          width={size.width}
          height={size.height}
          backgroundColor="#020617"
          showNavInfo={false}
          nodeLabel={(node: RenderNode) => node.label}
          nodeVal={(node: RenderNode) => sizeForNode(node, highlightNodeId)}
          nodeThreeObject={(node: RenderNode) =>
            createNodeObject(node, colorForNode(node, highlightNodeId, neighborIds), sizeForNode(node, highlightNodeId))
          }
          nodeThreeObjectExtend={false}
          linkSource="source"
          linkTarget="target"
          linkColor={(link: RenderLink) => {
            if (!selectedGraphId) {
              return "rgba(148, 163, 184, 0.28)";
            }
            return sourceIdOf(link) === selectedGraphId || targetIdOf(link) === selectedGraphId
              ? "rgba(125, 211, 252, 0.78)"
              : "rgba(71, 85, 105, 0.16)";
          }}
          linkWidth={(link: RenderLink) => {
            if (!selectedGraphId) {
              return 0.8;
            }
            return sourceIdOf(link) === selectedGraphId || targetIdOf(link) === selectedGraphId ? 2 : 0.35;
          }}
          linkDirectionalArrowLength={3.5}
          linkDirectionalArrowRelPos={1}
          linkDirectionalParticles={0}
          linkDirectionalParticleWidth={1.8}
          enableNodeDrag={false}
          enablePointerInteraction
          onNodeClick={(node) => onNodeClick?.(node.original)}
          onNodeDragEnd={(node) => {
            node.fx = node.x;
            node.fy = node.y;
            node.fz = node.z;
          }}
          d3VelocityDecay={0.38}
          d3AlphaDecay={0.025}
          cooldownTicks={120}
          controlType="orbit"
        />
      ) : null}

      <div className="absolute bottom-5 left-1/2 z-20 flex -translate-x-1/2 overflow-hidden rounded-lg border border-white/10 bg-slate-950/70 shadow-2xl backdrop-blur-md">
        <button
          type="button"
          onClick={() => handleZoom(1.35)}
          className="flex h-11 w-12 items-center justify-center border-r border-white/10 text-slate-100 transition-colors hover:bg-white/10"
          aria-label="缩小图谱"
          title="缩小"
        >
          <ZoomOut className="h-5 w-5" />
        </button>
        <button
          type="button"
          onClick={handleResetView}
          className="flex h-11 w-12 items-center justify-center border-r border-white/10 text-slate-100 transition-colors hover:bg-white/10"
          aria-label="重置图谱视角"
          title="重置视角"
        >
          <RotateCcw className="h-5 w-5" />
        </button>
        <button
          type="button"
          onClick={() => handleZoom(0.72)}
          className="flex h-11 w-12 items-center justify-center text-slate-100 transition-colors hover:bg-white/10"
          aria-label="放大图谱"
          title="放大"
        >
          <ZoomIn className="h-5 w-5" />
        </button>
      </div>
    </div>
  );
}
