/**
 * Frontend-owned normalized graph models derived from backend `/api/*` payloads.
 */
export interface GraphNode {
  id: number;
  url: string;
  domain: string;
  title: string | null;
  iconUrl: string | null;
  description?: string | null;
  x?: number;
  y?: number;
  degree?: number;
  incomingCount?: number;
  outgoingCount?: number;
  priorityScore?: number;
  componentId?: string;
}

export interface GraphEdge {
  id: string;
  source: number;
  target: number;
  linkText: string | null;
  linkUrlRaw: string;
}

export interface GraphMeta {
  strategy: string;
  limit: number;
  focusNodeId?: number | null;
  hops?: number | null;
  hasStablePositions?: boolean;
  snapshotVersion?: string;
  generatedAt?: string;
  source?: string;
  totalNodes?: number;
  totalEdges?: number;
  availableNodes?: number;
  availableEdges?: number;
  selectedNodes?: number;
  selectedEdges?: number;
  snapshotNamespace?: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  meta?: GraphMeta;
}

export interface LookupResult {
  queryUrl: string;
  normalizedQueryUrl: string;
  matchReason: string | null;
  totalMatches: number;
  items: GraphNode[];
}

export interface RecommendedBlog extends GraphNode {
  viaBlogs: GraphNode[];
}

export interface BlogDetail extends GraphNode {
  incomingLinks: number;
  outgoingLinks: number;
  relatedNodes: GraphNode[];
  recommendedBlogs: RecommendedBlog[];
}

export interface StatsData {
  totalNodes: number;
  totalEdges: number;
}
