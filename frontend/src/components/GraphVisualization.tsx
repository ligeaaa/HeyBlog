import { RotateCcw, ZoomIn, ZoomOut } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ForceGraph3D, { type ForceGraphMethods } from "react-force-graph-3d";
import * as THREE from "three";
import { resolveIconProxyUrl } from "../lib/icon";
import type { GraphData, GraphEdge, GraphNode } from "../types/graph";

export const GRAPH_RENDER_COOLDOWN_TICKS = 120;
const GRAPH_RENDER_MIN_STABILITY_TICKS = 80;
const GRAPH_RENDER_STABLE_SAMPLE_TICKS = 20;
const GRAPH_RENDER_AVERAGE_MOVEMENT_THRESHOLD = 0.15;
const GRAPH_RENDER_MAX_MOVEMENT_THRESHOLD = 1;
const GRAPH_LINK_DISTANCE = 96;
const GRAPH_LINK_STRENGTH = 0.24;
const GRAPH_CHARGE_STRENGTH = -280;
const GRAPH_CHARGE_DISTANCE_MAX = 1400;
const GRAPH_SEEDED_GROUP_SIZE = 18;
const GRAPH_SEEDED_LAYOUT_SPACING = 360;

interface GraphVisualizationProps {
  data: GraphData;
  onNodeClick?: (node: GraphNode) => void;
  highlightNodeId?: number;
  onRenderProgress?: (progress: number) => void;
  onRenderComplete?: () => void;
  onRenderTickEstimate?: (ticks: number) => void;
  useNodeIcons?: boolean;
}

interface RenderNode extends Omit<GraphNode, "id" | "iconUrl"> {
  id: string;
  blogId: number;
  original: GraphNode;
  label: string;
  val: number;
  iconUrl?: string;
  iconUrls: string[];
}

interface RenderLink extends Omit<GraphEdge, "source" | "target"> {
  source: string | RenderNode;
  target: string | RenderNode;
}

interface RenderGraphData {
  nodes: RenderNode[];
  links: RenderLink[];
}

interface NodePosition {
  x: number;
  y: number;
  z: number;
}

interface MovementSample {
  averageMovement: number;
  maxMovement: number;
  measuredNodes: number;
}

function nodeTitle(node: GraphNode): string {
  return node.title?.trim() || node.domain || node.url || `Blog ${node.id}`;
}

/**
 * Keep one numeric value above an inclusive minimum.
 *
 * @param value Candidate value.
 * @param min Inclusive minimum.
 * @returns Value constrained to at least min.
 */
function clampMin(value: number, min: number): number {
  return Math.max(min, value);
}

/**
 * Estimate the maximum force-layout duration from graph size.
 *
 * @param nodeCount Number of renderable graph nodes.
 * @param edgeCount Number of renderable graph links.
 * @returns Cooldown tick upper bound used by the force graph engine.
 */
export function estimateGraphRenderCooldownTicks(nodeCount: number, edgeCount: number): number {
  const safeNodeCount = Math.max(0, nodeCount);
  const safeEdgeCount = Math.max(0, edgeCount);
  const edgeDensity = safeEdgeCount / Math.max(1, safeNodeCount);
  const estimatedTicks = Math.round(
    80 + 12 * Math.sqrt(safeNodeCount) + 4 * Math.sqrt(safeEdgeCount) + Math.min(180, edgeDensity * 18),
  );

  return clampMin(estimatedTicks, GRAPH_RENDER_COOLDOWN_TICKS);
}

/**
 * Capture the current 3D positions for nodes that have been placed by d3.
 *
 * @param nodes Render nodes from the active graph payload.
 * @returns Map keyed by render node id with current coordinates.
 */
function snapshotNodePositions(nodes: RenderNode[]): Map<string, NodePosition> {
  const positions = new Map<string, NodePosition>();
  for (const node of nodes) {
    if (node.x === undefined || node.y === undefined || node.z === undefined) {
      continue;
    }
    positions.set(node.id, { x: node.x, y: node.y, z: node.z });
  }
  return positions;
}

/**
 * Measure node displacement since the previous force tick.
 *
 * @param nodes Render nodes from the active graph payload.
 * @param previousPositions Position snapshot from the previous tick.
 * @returns Average and maximum displacement, or undefined when no positions are available.
 */
function measureNodeMovement(nodes: RenderNode[], previousPositions: Map<string, NodePosition>): MovementSample | undefined {
  let totalMovement = 0;
  let maxMovement = 0;
  let measuredNodes = 0;

  for (const node of nodes) {
    const previous = previousPositions.get(node.id);
    if (!previous || node.x === undefined || node.y === undefined || node.z === undefined) {
      continue;
    }

    const movement = Math.hypot(node.x - previous.x, node.y - previous.y, node.z - previous.z);
    totalMovement += movement;
    maxMovement = Math.max(maxMovement, movement);
    measuredNodes += 1;
  }

  if (measuredNodes === 0) {
    return undefined;
  }

  return {
    averageMovement: totalMovement / measuredNodes,
    maxMovement,
    measuredNodes,
  };
}

function sourceIdOf(link: RenderLink): string {
  return typeof link.source === "object" ? link.source.id : String(link.source);
}

function targetIdOf(link: RenderLink): string {
  return typeof link.target === "object" ? link.target.id : String(link.target);
}

/**
 * Build an undirected adjacency map from renderable links.
 *
 * @param nodes Nodes that can be displayed in the graph.
 * @param links Links whose endpoints both exist in the graph.
 * @returns Map keyed by node id with neighboring node ids.
 */
function buildAdjacency(nodes: RenderNode[], links: RenderLink[]): Map<string, Set<string>> {
  const adjacency = new Map<string, Set<string>>();
  for (const node of nodes) {
    adjacency.set(node.id, new Set());
  }

  for (const link of links) {
    const source = sourceIdOf(link);
    const target = targetIdOf(link);
    if (source === target || !adjacency.has(source) || !adjacency.has(target)) {
      continue;
    }
    adjacency.get(source)?.add(target);
    adjacency.get(target)?.add(source);
  }

  return adjacency;
}

/**
 * Find deterministic weakly connected components for initial graph placement.
 *
 * @param nodes Nodes that can be displayed in the graph.
 * @param adjacency Undirected adjacency map.
 * @returns Components sorted by size and id for stable layout.
 */
function findConnectedComponents(nodes: RenderNode[], adjacency: Map<string, Set<string>>): string[][] {
  const visited = new Set<string>();
  const nodeIds = nodes.map((node) => node.id).sort((left, right) => Number(left) - Number(right));
  const components: string[][] = [];

  for (const nodeId of nodeIds) {
    if (visited.has(nodeId)) {
      continue;
    }

    const component: string[] = [];
    const queue = [nodeId];
    visited.add(nodeId);

    for (let index = 0; index < queue.length; index += 1) {
      const current = queue[index];
      component.push(current);
      const neighbors = Array.from(adjacency.get(current) ?? []).sort((left, right) => Number(left) - Number(right));
      for (const neighbor of neighbors) {
        if (visited.has(neighbor)) {
          continue;
        }
        visited.add(neighbor);
        queue.push(neighbor);
      }
    }

    components.push(component);
  }

  return components.sort((left, right) => right.length - left.length || Number(left[0]) - Number(right[0]));
}

/**
 * Split a large connected component into deterministic layout groups.
 *
 * @param component Node ids in one connected component.
 * @param adjacency Undirected adjacency map.
 * @returns Layout groups used only for initial spatial seeding.
 */
function splitComponentIntoLayoutGroups(component: string[], adjacency: Map<string, Set<string>>): string[][] {
  if (component.length <= GRAPH_SEEDED_GROUP_SIZE) {
    return [component];
  }

  const seedCount = Math.max(2, Math.ceil(component.length / GRAPH_SEEDED_GROUP_SIZE));
  const componentIds = new Set(component);
  const seeds = component
    .slice()
    .sort((left, right) => {
      const degreeDelta = (adjacency.get(right)?.size ?? 0) - (adjacency.get(left)?.size ?? 0);
      return degreeDelta || Number(left) - Number(right);
    })
    .slice(0, seedCount);

  const groupByNodeId = new Map<string, number>();
  const queues = seeds.map((seed, index) => {
    groupByNodeId.set(seed, index);
    return [seed];
  });

  for (let queueIndex = 0; queues.some((queue) => queue.length > 0); queueIndex = (queueIndex + 1) % queues.length) {
    const current = queues[queueIndex].shift();
    if (!current) {
      continue;
    }

    const neighbors = Array.from(adjacency.get(current) ?? []).sort((left, right) => Number(left) - Number(right));
    for (const neighbor of neighbors) {
      if (!componentIds.has(neighbor) || groupByNodeId.has(neighbor)) {
        continue;
      }
      groupByNodeId.set(neighbor, queueIndex);
      queues[queueIndex].push(neighbor);
    }
  }

  const groups = seeds.map((): string[] => []);
  for (const nodeId of component) {
    const groupIndex = groupByNodeId.get(nodeId) ?? 0;
    groups[groupIndex].push(nodeId);
  }

  return groups.filter((group) => group.length > 0);
}

/**
 * Seed deterministic 3D positions so force layout starts from separated regions.
 *
 * @param nodes Nodes to position.
 * @param links Links used to infer components and layout groups.
 * @returns Nodes with initial x/y/z coordinates.
 */
export function seedGraphInitialPositions(nodes: RenderNode[], links: RenderLink[]): RenderNode[] {
  const adjacency = buildAdjacency(nodes, links);
  const layoutGroups = findConnectedComponents(nodes, adjacency).flatMap((component) =>
    splitComponentIntoLayoutGroups(component, adjacency),
  );
  const groupIndexByNodeId = new Map<string, number>();
  for (const [groupIndex, group] of layoutGroups.entries()) {
    for (const nodeId of group) {
      groupIndexByNodeId.set(nodeId, groupIndex);
    }
  }

  const nodeIndexInGroup = new Map<string, number>();
  for (const group of layoutGroups) {
    const sortedGroup = group.slice().sort((left, right) => Number(left) - Number(right));
    sortedGroup.forEach((nodeId, index) => nodeIndexInGroup.set(nodeId, index));
  }

  const groupCount = Math.max(1, layoutGroups.length);
  return nodes.map((node) => {
    const groupIndex = groupIndexByNodeId.get(node.id) ?? 0;
    const indexInGroup = nodeIndexInGroup.get(node.id) ?? 0;
    const groupSize = Math.max(1, layoutGroups[groupIndex]?.length ?? 1);
    const groupAngle = (Math.PI * 2 * groupIndex) / groupCount;
    const groupRing = GRAPH_SEEDED_LAYOUT_SPACING * (1 + Math.floor(groupIndex / Math.max(1, Math.ceil(Math.sqrt(groupCount)))));
    const localAngle = (Math.PI * 2 * indexInGroup) / groupSize;
    const localRadius = 34 + 8 * Math.sqrt(groupSize) + 5 * (indexInGroup % 5);

    return {
      ...node,
      x: Math.cos(groupAngle) * groupRing + Math.cos(localAngle) * localRadius,
      y: Math.sin(groupAngle) * groupRing + Math.sin(localAngle) * localRadius,
      z: ((indexInGroup % 7) - 3) * 24 + (groupIndex % 3) * 60,
    };
  });
}

function buildExplicitIconUrls(node: GraphNode, useNodeIcons: boolean): string[] {
  const iconUrl = node.iconUrl?.trim();
  if (!useNodeIcons || !iconUrl) {
    return [];
  }
  return [resolveIconProxyUrl(iconUrl)];
}

function buildGraphData(data: GraphData, useNodeIcons: boolean): RenderGraphData {
  const nodesById = new Map<string, RenderNode>();

  for (const node of data.nodes) {
    const id = String(node.id).trim();
    if (!id) {
      continue;
    }
    const iconUrls = buildExplicitIconUrls(node, useNodeIcons);
    nodesById.set(id, {
      ...node,
      id,
      blogId: node.id,
      original: node,
      label: nodeTitle(node),
      val: 1,
      iconUrls,
      iconUrl: iconUrls[0],
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

  return { nodes: seedGraphInitialPositions(nodes, links), links };
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
  group.userData = { blogId: node.blogId, iconUrl: node.iconUrl };

  const iconUrls = node.iconUrls.length > 0 ? node.iconUrls : node.iconUrl ? [node.iconUrl] : [];
  if (iconUrls.length > 0) {
    const loader = new THREE.TextureLoader();
    loader.setCrossOrigin("anonymous");
    const texture = new THREE.Texture();
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

    const loadIcon = (index: number) => {
      const candidate = iconUrls[index];
      if (!candidate) {
        core.visible = true;
        icon.visible = false;
        return;
      }
      loader.load(
        candidate,
        (loadedTexture) => {
          loadedTexture.colorSpace = THREE.SRGBColorSpace;
          icon.material.map = loadedTexture;
          icon.material.needsUpdate = true;
          core.visible = false;
          icon.visible = true;
          group.userData.iconUrl = candidate;
        },
        undefined,
        () => loadIcon(index + 1),
      );
    };
    loadIcon(0);
  }

  return group;
}

/**
 * Tune the d3 force engine so related blogs cluster without collapsing into a global sphere.
 *
 * @param graph Force graph instance exposed by react-force-graph-3d.
 */
export function tuneNaturalClusterForces(graph: ForceGraphMethods<RenderNode, RenderLink>): void {
  graph.d3Force("center", null);

  const chargeForce = graph.d3Force("charge") as
    | {
        strength?: (value: number) => unknown;
        distanceMax?: (value: number) => unknown;
      }
    | undefined;
  chargeForce?.strength?.(GRAPH_CHARGE_STRENGTH);
  chargeForce?.distanceMax?.(GRAPH_CHARGE_DISTANCE_MAX);

  const linkForce = graph.d3Force("link") as
    | {
        distance?: (value: number) => unknown;
        strength?: (value: number) => unknown;
      }
    | undefined;
  linkForce?.distance?.(GRAPH_LINK_DISTANCE);
  linkForce?.strength?.(GRAPH_LINK_STRENGTH);
  graph.d3ReheatSimulation();
}

/**
 * Render an interactive 3D force graph for blog relationship exploration.
 *
 * @param data Graph payload normalized from backend APIs.
 * @param onNodeClick Optional callback fired with the original graph node.
 * @param highlightNodeId Selected node id to emphasize.
 * @returns Graph container with 3D canvas and controls.
 */
export function GraphVisualization({
  data,
  onNodeClick,
  highlightNodeId,
  onRenderProgress,
  onRenderComplete,
  onRenderTickEstimate,
  useNodeIcons = true,
}: GraphVisualizationProps) {
  const graphRef = useRef<ForceGraphMethods<RenderNode, RenderLink> | undefined>(undefined);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const renderTickRef = useRef(0);
  const stableTickRef = useRef(0);
  const earlyStopRequestedRef = useRef(false);
  const previousPositionsRef = useRef<Map<string, NodePosition>>(new Map());
  const [size, setSize] = useState({ width: 960, height: 720 });
  const [isMeasured, setIsMeasured] = useState(false);
  const graphData = useMemo(() => buildGraphData(data, useNodeIcons), [data, useNodeIcons]);
  const estimatedCooldownTicks = useMemo(
    () => estimateGraphRenderCooldownTicks(graphData.nodes.length, graphData.links.length),
    [graphData.links.length, graphData.nodes.length],
  );
  const [cooldownTicks, setCooldownTicks] = useState(estimatedCooldownTicks);
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
    renderTickRef.current = 0;
    stableTickRef.current = 0;
    earlyStopRequestedRef.current = false;
    previousPositionsRef.current = snapshotNodePositions(graphData.nodes);
    setCooldownTicks(estimatedCooldownTicks);
    onRenderTickEstimate?.(estimatedCooldownTicks);
  }, [estimatedCooldownTicks, graphData, onRenderTickEstimate]);

  useEffect(() => {
    const graph = graphRef.current;
    if (!graph || graphData.nodes.length === 0) {
      return;
    }
    tuneNaturalClusterForces(graph);
  }, [graphData]);

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

  const handleEngineTick = useCallback(() => {
    renderTickRef.current += 1;
    const movement = measureNodeMovement(graphData.nodes, previousPositionsRef.current);
    previousPositionsRef.current = snapshotNodePositions(graphData.nodes);

    if (
      movement &&
      renderTickRef.current >= GRAPH_RENDER_MIN_STABILITY_TICKS &&
      movement.averageMovement < GRAPH_RENDER_AVERAGE_MOVEMENT_THRESHOLD &&
      movement.maxMovement < GRAPH_RENDER_MAX_MOVEMENT_THRESHOLD
    ) {
      stableTickRef.current += 1;
    } else {
      stableTickRef.current = 0;
    }

    if (!earlyStopRequestedRef.current && stableTickRef.current >= GRAPH_RENDER_STABLE_SAMPLE_TICKS) {
      earlyStopRequestedRef.current = true;
      setCooldownTicks((current) => Math.min(current, renderTickRef.current));
    }

    onRenderProgress?.(Math.min(renderTickRef.current / cooldownTicks, 0.98));
  }, [cooldownTicks, graphData.nodes, onRenderProgress]);

  const handleEngineStop = useCallback(() => {
    onRenderProgress?.(1);
    onRenderComplete?.();
  }, [onRenderComplete, onRenderProgress]);

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
              return "rgba(224, 242, 254, 0.78)";
            }
            return sourceIdOf(link) === selectedGraphId || targetIdOf(link) === selectedGraphId
              ? "rgba(240, 249, 255, 1)"
              : "rgba(186, 230, 253, 0.55)";
          }}
          linkWidth={(link: RenderLink) => {
            if (!selectedGraphId) {
              return 1.6;
            }
            return sourceIdOf(link) === selectedGraphId || targetIdOf(link) === selectedGraphId ? 3.2 : 0.9;
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
          d3VelocityDecay={0.44}
          d3AlphaDecay={0.025}
          cooldownTicks={cooldownTicks}
          onEngineTick={handleEngineTick}
          onEngineStop={handleEngineStop}
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
