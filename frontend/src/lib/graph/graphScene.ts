import type { EdgeRecord, GraphNodeRecord, GraphViewPayload } from "../api";

export type GraphPoint = {
  x: number;
  y: number;
};

export type GraphNodeDetails = {
  id: string;
  label: string;
  url: string;
  domain: string;
  title: string | null;
  iconUrl: string | null;
  friendLinks: number;
  outgoingCount: number;
  incomingCount: number;
  degree: number;
  crawlStatus: string;
  componentId: string | null;
  priorityScore: number;
};

export type GraphSceneNode = {
  id: string;
  label: string;
  domain: string;
  iconUrl: string | null;
  degree: number;
  incomingCount: number;
  outgoingCount: number;
  position: GraphPoint;
  basePosition: GraphPoint;
  visual: {
    isHeavy: boolean;
    showLabel: boolean;
    hasIcon: boolean;
  };
};

export type GraphSceneEdge = {
  id: string;
  source: string;
  target: string;
  label: string;
};

export type GraphPositionOverlay = {
  graphFingerprint: string | null;
  positions: Map<string, GraphPoint>;
};

export type GraphScene = {
  nodes: GraphSceneNode[];
  edges: GraphSceneEdge[];
  detailsById: Map<string, GraphNodeDetails>;
  signature: string;
  hasStablePositions: boolean;
  shouldRunLayout: boolean;
  graphFingerprint: string | null;
  performanceMode: {
    reduceEdgeDetail: boolean;
    reduceLabels: boolean;
    labelDegreeThreshold: number;
  };
};

const LABEL_DEGREE_THRESHOLD = 5;
const REDUCED_LABEL_DEGREE_THRESHOLD = 8;
const HIDE_EDGES_THRESHOLD = 800;
const REDUCE_LABELS_THRESHOLD = 220;

function labelForNode(node: GraphNodeRecord) {
  return node.title?.trim() || node.domain;
}

function seedPosition(nodeIndex: number, nodeCount: number): GraphPoint {
  const angle = (Math.PI * 2 * nodeIndex) / Math.max(nodeCount, 1);
  return {
    x: 420 + Math.cos(angle) * 220,
    y: 320 + Math.sin(angle) * 220,
  };
}

function hasPresetPosition(node: GraphNodeRecord) {
  return Number.isFinite(node.x) && Number.isFinite(node.y);
}

function canRestoreOverlay(payload: GraphViewPayload | null | undefined, overlay?: GraphPositionOverlay) {
  if (!payload || !overlay) {
    return false;
  }
  return (payload.meta.graph_fingerprint ?? null) === overlay.graphFingerprint;
}

export function createEmptyGraphOverlay(): GraphPositionOverlay {
  return {
    graphFingerprint: null,
    positions: new Map(),
  };
}

export function mergeGraphViewPayload(
  base: GraphViewPayload | null,
  addition: GraphViewPayload,
): GraphViewPayload {
  if (!base) {
    return addition;
  }

  const nodeMap = new Map<number, GraphNodeRecord>();
  for (const node of [...base.nodes, ...addition.nodes]) {
    nodeMap.set(node.id, node);
  }

  const edgeMap = new Map<number, EdgeRecord>();
  for (const edge of [...base.edges, ...addition.edges]) {
    edgeMap.set(edge.id, edge);
  }

  return {
    nodes: Array.from(nodeMap.values()),
    edges: Array.from(edgeMap.values()),
    meta: {
      ...addition.meta,
      selected_nodes: nodeMap.size,
      selected_edges: edgeMap.size,
    },
  };
}

export function buildGraphScene(
  payload?: GraphViewPayload | null,
  overlay?: GraphPositionOverlay,
): GraphScene {
  const nodes = payload?.nodes ?? [];
  const edges = payload?.edges ?? [];
  const hasStablePositions = payload?.meta.has_stable_positions ?? false;
  const shouldUseOverlay = canRestoreOverlay(payload, overlay);
  const reduceLabels = nodes.length > REDUCE_LABELS_THRESHOLD || edges.length > HIDE_EDGES_THRESHOLD;
  const detailsById = new Map<string, GraphNodeDetails>();

  const sceneNodes = nodes.map((node, nodeIndex) => {
    const nodeId = String(node.id);
    const degree = node.degree ?? 0;
    const label = labelForNode(node);
    const basePosition =
      hasPresetPosition(node) && hasStablePositions
        ? { x: Number(node.x), y: Number(node.y) }
        : seedPosition(nodeIndex, nodes.length);
    const overlayPosition = shouldUseOverlay ? overlay?.positions.get(nodeId) : undefined;
    const position = overlayPosition ?? basePosition;

    detailsById.set(nodeId, {
      id: nodeId,
      label,
      url: node.url,
      domain: node.domain,
      title: node.title ?? null,
      iconUrl: node.icon_url ?? null,
      friendLinks: node.friend_links_count,
      outgoingCount: node.outgoing_count ?? 0,
      incomingCount: node.incoming_count ?? 0,
      degree,
      crawlStatus: node.crawl_status,
      componentId: node.component_id ?? null,
      priorityScore: node.priority_score ?? 0,
    });

    return {
      id: nodeId,
      label,
      domain: node.domain,
      iconUrl: node.icon_url ?? null,
      degree,
      incomingCount: node.incoming_count ?? 0,
      outgoingCount: node.outgoing_count ?? 0,
      position,
      basePosition,
      visual: {
        isHeavy: degree >= 8,
        showLabel: degree >= LABEL_DEGREE_THRESHOLD,
        hasIcon: Boolean(node.icon_url),
      },
    } satisfies GraphSceneNode;
  });

  const sceneEdges = edges.map(
    (edge) =>
      ({
        id: String(edge.id),
        source: String(edge.from_blog_id),
        target: String(edge.to_blog_id),
        label: edge.link_text ?? "",
      }) satisfies GraphSceneEdge,
  );

  return {
    nodes: sceneNodes,
    edges: sceneEdges,
    detailsById,
    signature: JSON.stringify({
      strategy: payload?.meta.strategy ?? "degree",
      limit: payload?.meta.limit ?? null,
      focusNodeId: payload?.meta.focus_node_id ?? null,
      hops: payload?.meta.hops ?? null,
      source: payload?.meta.source ?? null,
      snapshotVersion: payload?.meta.snapshot_version ?? null,
      graphFingerprint: payload?.meta.graph_fingerprint ?? null,
      selectedNodeIds: nodes.map((node) => node.id),
      selectedEdgeIds: edges.map((edge) => edge.id),
      nodeLabels: nodes.map((node) => [node.id, node.title ?? node.domain, node.icon_url ?? null]),
      nodePositions: sceneNodes.map((node) => [node.id, node.position.x, node.position.y]),
      sampleMode: payload?.meta.sample_mode ?? "off",
      sampleValue: payload?.meta.sample_value ?? null,
    }),
    hasStablePositions,
    shouldRunLayout: !hasStablePositions,
    graphFingerprint: payload?.meta.graph_fingerprint ?? null,
    performanceMode: {
      reduceEdgeDetail: sceneEdges.length > HIDE_EDGES_THRESHOLD,
      reduceLabels,
      labelDegreeThreshold: reduceLabels ? REDUCED_LABEL_DEGREE_THRESHOLD : LABEL_DEGREE_THRESHOLD,
    },
  };
}
