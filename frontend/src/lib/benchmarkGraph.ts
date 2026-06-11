import type { GraphData, GraphEdge, GraphMeta, GraphNode } from "../types/graph";

interface BenchmarkGraphNodePayload {
  id: number;
  url: string;
  domain: string;
  title: string | null;
  icon_url: string | null;
  incoming_count?: number;
  outgoing_count?: number;
  degree?: number;
  component_id?: string;
  x?: number;
  y?: number;
  z?: number;
}

interface BenchmarkGraphEdgePayload {
  id?: number | string;
  from_blog_id: number;
  to_blog_id: number;
  link_text: string | null;
  link_url_raw: string;
}

interface BenchmarkGraphPayload {
  nodes: BenchmarkGraphNodePayload[];
  edges: BenchmarkGraphEdgePayload[];
  meta?: {
    strategy: string;
    limit: number;
    generated_at?: string;
    source?: string;
    total_nodes?: number;
    total_edges?: number;
    available_nodes?: number;
    available_edges?: number;
    selected_nodes?: number;
    selected_edges?: number;
  };
}

/**
 * Convert a static benchmark node payload to the frontend graph node model.
 *
 * @param node Raw benchmark node using backend field names.
 * @returns Normalized graph node.
 */
function toBenchmarkNode(node: BenchmarkGraphNodePayload): GraphNode {
  return {
    id: Number(node.id),
    url: node.url,
    domain: node.domain,
    title: node.title,
    iconUrl: node.icon_url,
    incomingCount: node.incoming_count,
    outgoingCount: node.outgoing_count,
    degree: node.degree,
    componentId: node.component_id,
    x: node.x,
    y: node.y,
    z: node.z,
  };
}

/**
 * Convert a static benchmark edge payload to the frontend graph edge model.
 *
 * @param edge Raw benchmark edge using backend field names.
 * @param index Fallback edge index.
 * @returns Normalized graph edge.
 */
function toBenchmarkEdge(edge: BenchmarkGraphEdgePayload, index: number): GraphEdge {
  return {
    id: edge.id ? String(edge.id) : `benchmark-edge-${index}`,
    source: Number(edge.from_blog_id),
    target: Number(edge.to_blog_id),
    linkText: edge.link_text,
    linkUrlRaw: edge.link_url_raw,
  };
}

/**
 * Convert static benchmark metadata to the frontend graph meta model.
 *
 * @param meta Raw benchmark metadata.
 * @returns Normalized graph metadata.
 */
function toBenchmarkMeta(meta: BenchmarkGraphPayload["meta"]): GraphMeta | undefined {
  if (!meta) {
    return undefined;
  }
  return {
    strategy: meta.strategy,
    limit: meta.limit,
    generatedAt: meta.generated_at,
    source: meta.source,
    totalNodes: meta.total_nodes,
    totalEdges: meta.total_edges,
    availableNodes: meta.available_nodes,
    availableEdges: meta.available_edges,
    selectedNodes: meta.selected_nodes,
    selectedEdges: meta.selected_edges,
  };
}

/**
 * Fetch the static visualization benchmark graph.
 *
 * @returns Normalized graph data for the shared 3D visualization component.
 */
export async function fetchBenchmarkGraphData(): Promise<GraphData> {
  const response = await fetch("/benchmarks/blog-community-graph.json", {
    headers: {
      accept: "application/json",
    },
  });
  if (!response.ok) {
    throw new Error(`benchmark_graph_error_${response.status}`);
  }

  const payload = (await response.json()) as BenchmarkGraphPayload;
  return {
    nodes: payload.nodes.map(toBenchmarkNode),
    edges: payload.edges.map(toBenchmarkEdge),
    meta: toBenchmarkMeta(payload.meta),
  };
}
