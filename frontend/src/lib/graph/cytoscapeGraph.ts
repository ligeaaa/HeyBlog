import type cytoscape from "cytoscape";
import type { EdgeRecord, GraphNodeRecord, GraphViewPayload } from "../api";

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

export type GraphBundle = {
  elements: cytoscape.ElementDefinition[];
  detailsById: Map<string, GraphNodeDetails>;
  signature: string;
  hasStablePositions: boolean;
  shouldRunLayout: boolean;
};

function labelForNode(node: GraphNodeRecord) {
  return node.title?.trim() || node.domain;
}

function seedPosition(nodeIndex: number, nodeCount: number) {
  const angle = (Math.PI * 2 * nodeIndex) / Math.max(nodeCount, 1);
  return {
    x: 420 + Math.cos(angle) * 220,
    y: 320 + Math.sin(angle) * 220,
  };
}

function hasPresetPosition(node: GraphNodeRecord) {
  return Number.isFinite(node.x) && Number.isFinite(node.y);
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

export function buildCytoscapeGraph(
  payload?: GraphViewPayload | null,
  cachedPositions?: Map<string, { x: number; y: number }>,
): GraphBundle {
  const nodes = payload?.nodes ?? [];
  const edges = payload?.edges ?? [];
  const hasStablePositions = payload?.meta.has_stable_positions ?? false;
  const detailsById = new Map<string, GraphNodeDetails>();

  const nodeElements = nodes.map((node, nodeIndex) => {
    const nodeId = String(node.id);
    const degree = node.degree ?? 0;
    const label = labelForNode(node);
    const shouldShowLabel = degree >= 5;

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

    const cachedPosition = cachedPositions?.get(nodeId);
    const position =
      hasPresetPosition(node) && hasStablePositions
        ? { x: Number(node.x), y: Number(node.y) }
        : cachedPosition ?? seedPosition(nodeIndex, nodes.length);

    return {
      data: {
        id: nodeId,
        label,
        domain: node.domain,
        iconUrl: node.icon_url ?? "",
        degree,
        outgoingCount: node.outgoing_count ?? 0,
        incomingCount: node.incoming_count ?? 0,
      },
      position,
      classes: [
        degree >= 8 ? "graph-node-heavy" : "",
        shouldShowLabel ? "graph-node-labeled" : "",
        node.icon_url ? "graph-node-has-icon" : "",
      ]
        .filter(Boolean)
        .join(" "),
    } satisfies cytoscape.ElementDefinition;
  });

  const edgeElements = edges.map((edge) => ({
    data: {
      id: String(edge.id),
      source: String(edge.from_blog_id),
      target: String(edge.to_blog_id),
      label: edge.link_text ?? "",
    },
  }) satisfies cytoscape.ElementDefinition);

  return {
    elements: [...nodeElements, ...edgeElements],
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
      nodePositions: nodes.map((node) => [node.id, node.x ?? null, node.y ?? null]),
      sampleMode: payload?.meta.sample_mode ?? "off",
      sampleValue: payload?.meta.sample_value ?? null,
    }),
    hasStablePositions,
    shouldRunLayout: !hasStablePositions,
  };
}

export const graphStylesheet: cytoscape.StylesheetJson = [
  {
    selector: "node",
    style: {
      label: "",
      width: "mapData(degree, 0, 20, 16, 40)",
      height: "mapData(degree, 0, 20, 16, 40)",
      "font-size": 10,
      "font-weight": 600,
      color: "#f5f8ff",
      "min-zoomed-font-size": 11,
      "text-wrap": "ellipsis",
      "text-max-width": "96px",
      "text-valign": "bottom",
      "text-margin-y": 12,
      "background-color": "#6aa4ff",
      "border-width": 1.5,
      "border-color": "rgba(237, 244, 255, 0.86)",
      "overlay-opacity": 0,
    },
  },
  {
    selector: "node.graph-node-labeled",
    style: {
      label: "data(label)",
    },
  },
  {
    selector: "node.graph-node-heavy",
    style: {
      "background-color": "#78e6c7",
    },
  },
  {
    selector: "node.graph-node-has-icon",
    style: {
      "background-image": "data(iconUrl)",
      "background-fit": "cover",
      "background-clip": "node",
      "background-width": "84%",
      "background-height": "84%",
      "background-image-opacity": 1,
    },
  },
  {
    selector: "node:selected",
    style: {
      label: "data(label)",
      "background-color": "#ffe49b",
      "border-color": "#ffffff",
      "border-width": 2.5,
      "text-outline-width": 2,
      "text-outline-color": "#0d1831",
      "z-index": 999,
    },
  },
  {
    selector: "edge",
    style: {
      width: 1.1,
      "line-color": "rgba(141, 181, 255, 0.24)",
      "curve-style": "haystack",
      opacity: 0.72,
    },
  },
  {
    selector: "edge:selected",
    style: {
      width: 2.2,
      "line-color": "#9fe0ff",
      opacity: 0.95,
    },
  },
];

export function createFcoseLayout(options: { animate?: boolean } = {}) {
  return {
    name: "fcose",
    quality: "draft",
    animate: options.animate ?? false,
    animationDuration: options.animate ? 600 : 0,
    randomize: false,
    fit: false,
    padding: 48,
    nodeRepulsion: 48000,
    idealEdgeLength: 110,
    edgeElasticity: 0.15,
    gravity: 0.2,
    gravityRangeCompound: 1.1,
    numIter: 500,
  } as unknown as cytoscape.LayoutOptions;
}
