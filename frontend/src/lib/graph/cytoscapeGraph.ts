import type cytoscape from "cytoscape";
import type { BlogRecord, GraphPayload } from "../api";

export type GraphNodeDetails = {
  id: string;
  label: string;
  url: string;
  domain: string;
  friendLinks: number;
  outgoingCount: number;
  incomingCount: number;
  degree: number;
  depth: number;
  crawlStatus: string;
};

export type GraphBundle = {
  elements: cytoscape.ElementDefinition[];
  detailsById: Map<string, GraphNodeDetails>;
  signature: string;
};

function labelForNode(node: BlogRecord) {
  const titledNode = node as BlogRecord & { title?: string };
  return titledNode.title?.trim() || node.domain;
}

function seedPosition(
  nodeIndex: number,
  nodeCount: number,
  cachedPosition?: { x: number; y: number },
) {
  if (cachedPosition) {
    return cachedPosition;
  }

  const angle = (Math.PI * 2 * nodeIndex) / Math.max(nodeCount, 1);
  return {
    x: 420 + Math.cos(angle) * 220,
    y: 320 + Math.sin(angle) * 220,
  };
}

export function buildCytoscapeGraph(
  payload?: GraphPayload,
  cachedPositions?: Map<string, { x: number; y: number }>,
): GraphBundle {
  const nodes = (payload?.nodes ?? []).filter((node) => node.crawl_status === "FINISHED");
  const finishedNodeIds = new Set(nodes.map((node) => node.id));
  const edges = (payload?.edges ?? []).filter(
    (edge) => finishedNodeIds.has(edge.from_blog_id) && finishedNodeIds.has(edge.to_blog_id),
  );
  const incoming = new Map<number, number>();
  const outgoing = new Map<number, number>();

  edges.forEach((edge) => {
    outgoing.set(edge.from_blog_id, (outgoing.get(edge.from_blog_id) ?? 0) + 1);
    incoming.set(edge.to_blog_id, (incoming.get(edge.to_blog_id) ?? 0) + 1);
  });

  const detailsById = new Map<string, GraphNodeDetails>();

  const nodeElements = nodes.map((node, nodeIndex) => {
    const incomingCount = incoming.get(node.id) ?? 0;
    const outgoingCount = outgoing.get(node.id) ?? 0;
    const degree = incomingCount + outgoingCount;
    const nodeId = String(node.id);
    const label = labelForNode(node);

    detailsById.set(nodeId, {
      id: nodeId,
      label,
      url: node.url,
      domain: node.domain,
      friendLinks: node.friend_links_count,
      outgoingCount,
      incomingCount,
      degree,
      depth: node.depth,
      crawlStatus: node.crawl_status,
    });

    return {
      data: {
        id: nodeId,
        label,
        domain: node.domain,
        depth: node.depth,
        degree,
        outgoingCount,
        incomingCount,
      },
      position: seedPosition(nodeIndex, nodes.length, cachedPositions?.get(nodeId)),
      classes: degree > 6 ? "graph-node-heavy" : undefined,
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
      nodeIds: nodes.map((node) => node.id),
      edgeIds: edges.map((edge) => edge.id),
    }),
  };
}

export const graphStylesheet: cytoscape.StylesheetJson = [
  {
    selector: "node",
    style: {
      label: "data(label)",
      width: "mapData(degree, 0, 10, 26, 54)",
      height: "mapData(degree, 0, 10, 26, 54)",
      "font-size": 11,
      "font-weight": 700,
      color: "#f5f8ff",
      "text-outline-width": 3,
      "text-outline-color": "#0d1831",
      "text-wrap": "wrap",
      "text-max-width": "90px",
      "text-valign": "bottom",
      "text-margin-y": 16,
      "background-color": "#6aa4ff",
      "border-width": 2,
      "border-color": "#edf4ff",
      "overlay-opacity": 0,
    },
  },
  {
    selector: "node.graph-node-heavy",
    style: {
      "background-color": "#78e6c7",
    },
  },
  {
    selector: "node:selected",
    style: {
      "background-color": "#ffba6f",
      "border-color": "#ffffff",
      "border-width": 3,
    },
  },
  {
    selector: "edge",
    style: {
      width: 1.8,
      "line-color": "rgba(141, 181, 255, 0.38)",
      "target-arrow-color": "rgba(141, 181, 255, 0.38)",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      opacity: 0.9,
    },
  },
  {
    selector: "edge:selected",
    style: {
      width: 2.8,
      "line-color": "#9fe0ff",
      "target-arrow-color": "#9fe0ff",
    },
  },
];

export function createFcoseLayout() {
  return {
    name: "fcose",
    quality: "default",
    animate: true,
    animationDuration: 900,
    randomize: false,
    fit: false,
    padding: 48,
    nodeRepulsion: 95000,
    idealEdgeLength: 130,
    edgeElasticity: 0.2,
    gravity: 0.22,
    gravityRangeCompound: 1.2,
    numIter: 1600,
  } as unknown as cytoscape.LayoutOptions;
}
