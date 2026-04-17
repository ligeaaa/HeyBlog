import type {
  BlogDetail,
  GraphData,
  GraphEdge,
  GraphMeta,
  GraphNode,
  LookupResult,
  RecommendedBlog,
  StatsData,
} from "../types/graph";

interface BackendGraphNode {
  id: number;
  url: string;
  domain: string;
  title: string | null;
  icon_url: string | null;
  x?: number;
  y?: number;
  degree?: number;
  incoming_count?: number;
  outgoing_count?: number;
  priority_score?: number;
  component_id?: string;
}

interface BackendGraphEdge {
  id?: number;
  from_blog_id: number;
  to_blog_id: number;
  link_text: string | null;
  link_url_raw: string;
}

interface BackendGraphPayload {
  nodes: BackendGraphNode[];
  edges: BackendGraphEdge[];
  meta?: {
    strategy: string;
    limit: number;
    focus_node_id?: number | null;
    hops?: number | null;
    has_stable_positions?: boolean;
    snapshot_version?: string;
    generated_at?: string;
    source?: string;
    total_nodes?: number;
    total_edges?: number;
    available_nodes?: number;
    available_edges?: number;
    selected_nodes?: number;
    selected_edges?: number;
    snapshot_namespace?: string;
  };
}

interface BackendBlogLookupPayload {
  query_url: string;
  normalized_query_url: string;
  match_reason: string | null;
  total_matches: number;
  items: BackendGraphNode[];
}

interface BackendNeighborSummary {
  id: number;
  domain: string;
  title: string | null;
  icon_url: string | null;
}

interface BackendBlogRelation {
  id: number;
  from_blog_id: number;
  to_blog_id: number;
  link_text: string | null;
  link_url_raw: string;
  neighbor_blog: BackendNeighborSummary | null;
}

interface BackendRecommendedBlog extends BackendGraphNode {
  via_blogs?: BackendNeighborSummary[];
}

interface BackendBlogDetail extends BackendGraphNode {
  incoming_edges: BackendBlogRelation[];
  outgoing_edges: BackendBlogRelation[];
  recommended_blogs: BackendRecommendedBlog[];
}

interface BackendStatsPayload {
  total_blogs: number;
  total_edges: number;
}

interface CreateIngestionRequestPayload {
  request_id: number;
  request_token: string;
  status: string;
}

function toGraphNode(node: BackendGraphNode | BackendNeighborSummary): GraphNode {
  return {
    id: Number(node.id),
    url: "url" in node ? node.url : "",
    domain: node.domain,
    title: node.title ?? null,
    iconUrl: node.icon_url ?? null,
    x: "x" in node ? node.x : undefined,
    y: "y" in node ? node.y : undefined,
    degree: "degree" in node ? node.degree : undefined,
    incomingCount: "incoming_count" in node ? node.incoming_count : undefined,
    outgoingCount: "outgoing_count" in node ? node.outgoing_count : undefined,
    priorityScore: "priority_score" in node ? node.priority_score : undefined,
    componentId: "component_id" in node ? node.component_id : undefined,
  };
}

function toGraphEdge(edge: BackendGraphEdge, index: number): GraphEdge {
  return {
    id: edge.id ? String(edge.id) : `edge-${edge.from_blog_id}-${edge.to_blog_id}-${index}`,
    source: Number(edge.from_blog_id),
    target: Number(edge.to_blog_id),
    linkText: edge.link_text ?? null,
    linkUrlRaw: edge.link_url_raw,
  };
}

function toGraphMeta(meta: BackendGraphPayload["meta"]): GraphMeta | undefined {
  if (!meta) {
    return undefined;
  }
  return {
    strategy: meta.strategy,
    limit: meta.limit,
    focusNodeId: meta.focus_node_id,
    hops: meta.hops,
    hasStablePositions: meta.has_stable_positions,
    snapshotVersion: meta.snapshot_version,
    generatedAt: meta.generated_at,
    source: meta.source,
    totalNodes: meta.total_nodes,
    totalEdges: meta.total_edges,
    availableNodes: meta.available_nodes,
    availableEdges: meta.available_edges,
    selectedNodes: meta.selected_nodes,
    selectedEdges: meta.selected_edges,
    snapshotNamespace: meta.snapshot_namespace,
  };
}

function toGraphData(payload: BackendGraphPayload): GraphData {
  return {
    nodes: payload.nodes.map(toGraphNode),
    edges: payload.edges.map(toGraphEdge),
    meta: toGraphMeta(payload.meta),
  };
}

async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    throw new Error(`api_error_${response.status}`);
  }
  return (await response.json()) as T;
}

export async function fetchGraphData(limit = 200): Promise<GraphData> {
  const params = new URLSearchParams({
    strategy: "degree",
    limit: String(limit),
  });
  const payload = await apiJson<BackendGraphPayload>(`/api/graph/views/core?${params.toString()}`);
  return toGraphData(payload);
}

export async function fetchBlogLookup(url: string): Promise<LookupResult> {
  const params = new URLSearchParams({ url });
  const payload = await apiJson<BackendBlogLookupPayload>(`/api/blogs/lookup?${params.toString()}`);
  return {
    queryUrl: payload.query_url,
    normalizedQueryUrl: payload.normalized_query_url,
    matchReason: payload.match_reason,
    totalMatches: payload.total_matches,
    items: payload.items.map(toGraphNode),
  };
}

export async function fetchBlogDetail(blogId: number): Promise<BlogDetail> {
  const payload = await apiJson<BackendBlogDetail>(`/api/blogs/${blogId}`);
  const incomingNeighbors = payload.incoming_edges
    .map((edge) => edge.neighbor_blog)
    .filter((neighbor): neighbor is BackendNeighborSummary => neighbor !== null)
    .map(toGraphNode);
  const outgoingNeighbors = payload.outgoing_edges
    .map((edge) => edge.neighbor_blog)
    .filter((neighbor): neighbor is BackendNeighborSummary => neighbor !== null)
    .map(toGraphNode);
  const relatedNodesById = new Map<number, GraphNode>();
  [...incomingNeighbors, ...outgoingNeighbors].forEach((node) => {
    relatedNodesById.set(node.id, node);
  });
  const recommendedBlogs: RecommendedBlog[] = payload.recommended_blogs.map((blog) => ({
    ...toGraphNode(blog),
    viaBlogs: (blog.via_blogs ?? []).map(toGraphNode),
  }));
  return {
    ...toGraphNode(payload),
    incomingLinks: payload.incoming_edges.length,
    outgoingLinks: payload.outgoing_edges.length,
    relatedNodes: Array.from(relatedNodesById.values()),
    recommendedBlogs,
  };
}

export async function fetchSubgraph(blogId: number, hops = 1, limit = 120): Promise<GraphData> {
  const params = new URLSearchParams({
    hops: String(hops),
    limit: String(limit),
  });
  const payload = await apiJson<BackendGraphPayload>(
    `/api/graph/nodes/${blogId}/neighbors?${params.toString()}`,
  );
  return toGraphData(payload);
}

export async function fetchStats(): Promise<StatsData> {
  const payload = await apiJson<BackendStatsPayload>("/api/stats");
  return {
    totalNodes: payload.total_blogs,
    totalEdges: payload.total_edges,
  };
}

export async function submitBlogInfo(data: {
  url: string;
  email: string;
}): Promise<CreateIngestionRequestPayload> {
  if (!data.url.trim()) {
    throw new Error("url_required");
  }
  if (!data.email.trim()) {
    throw new Error("email_required");
  }
  return apiJson<CreateIngestionRequestPayload>("/api/ingestion-requests", {
    method: "POST",
    body: JSON.stringify({
      homepage_url: data.url.trim(),
      email: data.email.trim(),
    }),
  });
}
