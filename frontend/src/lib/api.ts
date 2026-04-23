import type {
  AdminDedupSummary,
  AdminRuntimeCurrent,
  AdminRuntimeStatus,
  AdminUrlRefilterRun,
  AdminUrlRefilterRunEvent,
  BlogCatalogItem,
  BlogCatalogPage,
  BlogDetail,
  FilterStatsData,
  GraphData,
  GraphEdge,
  GraphMeta,
  GraphNode,
  LookupResult,
  RecommendedBlog,
  StatsData,
  StatusData,
} from "../types/graph";

interface BackendGraphNode {
  id: number;
  blog_id?: number;
  url: string;
  normalized_url?: string;
  identity_key?: string;
  identity_reason_codes?: string[];
  identity_ruleset_version?: string;
  domain: string;
  email?: string | null;
  title: string | null;
  icon_url: string | null;
  status_code?: number | null;
  crawl_status?: string;
  friend_links_count?: number;
  last_crawled_at?: string | null;
  created_at?: string;
  updated_at?: string;
  connection_count?: number;
  incoming_count?: number;
  outgoing_count?: number;
  activity_at?: string | null;
  identity_complete?: boolean;
  x?: number;
  y?: number;
  degree?: number;
  priority_score?: number;
  component_id?: string;
}

interface BackendGraphEdge {
  id?: number | string;
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
  blog_id?: number;
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

interface BackendStatusPayload {
  is_running: boolean;
  pending_tasks: number;
  processing_tasks: number;
  finished_tasks: number;
  failed_tasks: number;
  total_blogs: number;
  total_edges: number;
}

interface BackendFilterStatsPayload {
  by_filter_reason: Record<string, number>;
}

interface BackendCatalogPayload {
  items: BackendGraphNode[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
  sort: string;
}

interface CreateIngestionRequestPayload {
  request_id: number;
  request_token: string;
  status: string;
}

interface BackendRuntimePayload {
  runner_status: string;
  active_run_id: string | null;
  worker_count: number;
  active_workers: number;
  current_blog_id: number | null;
  current_url: string | null;
  current_stage: string | null;
  elapsed_seconds: number | null;
  maintenance_in_progress?: boolean;
}

interface BackendDedupSummary {
  id: number;
  status: string;
  total_count: number;
  scanned_count: number;
  removed_count: number;
  kept_count: number;
  created_at: string;
  updated_at: string;
}

interface BackendUrlRefilterRun {
  id: number;
  status: string;
  filter_chain_version: string;
  crawler_was_running: boolean;
  backup_path: string | null;
  total_count: number;
  scanned_count: number;
  unchanged_count: number;
  activated_count: number;
  deactivated_count: number;
  retagged_count: number;
  last_raw_url_id: number | null;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

interface BackendUrlRefilterRunEvent {
  id: number;
  run_id: number;
  message: string;
  created_at: string | null;
}

interface BlogCatalogQuery {
  page?: number;
  pageSize?: number;
  q?: string;
  sort?: string;
  site?: string;
  url?: string;
  status?: string;
  statuses?: string;
  hasTitle?: boolean;
  hasIcon?: boolean;
  minConnections?: number;
}

/**
 * Convert one backend graph node or neighbor summary to the normalized frontend node shape.
 *
 * @param node Raw backend node-like payload.
 * @returns Normalized graph node.
 */
function toGraphNode(node: BackendGraphNode | BackendNeighborSummary): GraphNode {
  const resolvedId = "blog_id" in node && typeof node.blog_id === "number" ? node.blog_id : node.id;
  return {
    id: Number(resolvedId),
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

/**
 * Convert one backend blog record into the home/admin catalog card model.
 *
 * @param node Raw backend blog record.
 * @returns Normalized catalog row.
 */
function toBlogCatalogItem(node: BackendGraphNode): BlogCatalogItem {
  return {
    ...toGraphNode(node),
    normalizedUrl: node.normalized_url ?? node.url,
    identityKey: node.identity_key ?? "",
    identityReasonCodes: node.identity_reason_codes ?? [],
    identityRulesetVersion: node.identity_ruleset_version ?? "",
    email: node.email ?? null,
    statusCode: node.status_code ?? null,
    crawlStatus: node.crawl_status ?? "WAITING",
    friendLinksCount: node.friend_links_count ?? 0,
    lastCrawledAt: node.last_crawled_at ?? null,
    createdAt: node.created_at ?? "",
    updatedAt: node.updated_at ?? "",
    incomingCount: node.incoming_count ?? 0,
    outgoingCount: node.outgoing_count ?? 0,
    connectionCount: node.connection_count ?? (node.incoming_count ?? 0) + (node.outgoing_count ?? 0),
    activityAt: node.activity_at ?? null,
    identityComplete: node.identity_complete ?? false,
  };
}

/**
 * Convert one backend edge to the normalized graph edge shape.
 *
 * @param edge Raw backend edge payload.
 * @param index Fallback index used when edge id is missing.
 * @returns Normalized graph edge.
 */
function toGraphEdge(edge: BackendGraphEdge, index: number): GraphEdge {
  return {
    id: edge.id ? String(edge.id) : `edge-${edge.from_blog_id}-${edge.to_blog_id}-${index}`,
    source: Number(edge.from_blog_id),
    target: Number(edge.to_blog_id),
    linkText: edge.link_text ?? null,
    linkUrlRaw: edge.link_url_raw,
  };
}

/**
 * Convert the optional backend graph meta payload into the normalized frontend shape.
 *
 * @param meta Raw backend graph meta.
 * @returns Normalized graph meta or undefined when absent.
 */
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

/**
 * Convert one graph payload into the normalized frontend graph data model.
 *
 * @param payload Raw backend graph payload.
 * @returns Normalized graph data.
 */
function toGraphData(payload: BackendGraphPayload): GraphData {
  return {
    nodes: payload.nodes.map(toGraphNode),
    edges: payload.edges.map(toGraphEdge),
    meta: toGraphMeta(payload.meta),
  };
}

/**
 * Convert one runtime payload into the normalized admin runtime model.
 *
 * @param payload Raw backend runtime payload.
 * @returns Normalized admin runtime state.
 */
function toRuntimePayload(payload: BackendRuntimePayload): AdminRuntimeStatus {
  return {
    runnerStatus: payload.runner_status,
    activeRunId: payload.active_run_id,
    workerCount: payload.worker_count,
    activeWorkers: payload.active_workers,
    currentBlogId: payload.current_blog_id,
    currentUrl: payload.current_url,
    currentStage: payload.current_stage,
    elapsedSeconds: payload.elapsed_seconds,
    maintenanceInProgress: Boolean(payload.maintenance_in_progress),
  };
}

/**
 * Build a standard JSON request against the frontend-served API surface.
 *
 * @param path Relative API path.
 * @param init Optional fetch init overrides.
 * @returns Parsed JSON payload.
 */
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

/**
 * Build authorization headers for protected admin requests.
 *
 * @param adminToken Raw admin token string.
 * @returns Fetch headers containing the bearer token.
 */
function adminHeaders(adminToken: string): HeadersInit {
  return {
    authorization: `Bearer ${adminToken.trim()}`,
  };
}

/**
 * Fetch the default core graph view.
 *
 * @param limit Maximum node count requested for the core graph.
 * @returns Normalized graph data.
 */
export async function fetchGraphData(limit = 200): Promise<GraphData> {
  const params = new URLSearchParams({
    strategy: "degree",
    limit: String(limit),
  });
  const payload = await apiJson<BackendGraphPayload>(`/api/graph/views/core?${params.toString()}`);
  return toGraphData(payload);
}

/**
 * Fetch one neighborhood graph around a selected blog.
 *
 * @param blogId Focus blog id.
 * @param hops Neighborhood hop count.
 * @param limit Maximum node count.
 * @returns Normalized graph data.
 */
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

/**
 * Look up one blog URL against the public discovery endpoint.
 *
 * @param url URL entered by the user.
 * @returns Lookup result containing zero, one, or many candidate blogs.
 */
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

/**
 * Fetch one blog detail payload.
 *
 * @param blogId Target blog id.
 * @returns Normalized blog detail.
 */
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

/**
 * Fetch the public graph-wide stats payload.
 *
 * @returns Normalized stats summary.
 */
export async function fetchStats(): Promise<StatsData> {
  const payload = await apiJson<BackendStatsPayload>("/api/stats");
  return {
    totalNodes: payload.total_blogs,
    totalEdges: payload.total_edges,
  };
}

/**
 * Fetch the public crawler summary status used by the homepage dashboard.
 *
 * @returns Normalized queue/runtime summary.
 */
export async function fetchStatus(): Promise<StatusData> {
  const payload = await apiJson<BackendStatusPayload>("/api/status");
  return {
    isRunning: payload.is_running,
    pendingTasks: payload.pending_tasks,
    processingTasks: payload.processing_tasks,
    finishedTasks: payload.finished_tasks,
    failedTasks: payload.failed_tasks,
    totalNodes: payload.total_blogs,
    totalEdges: payload.total_edges,
  };
}

/**
 * Fetch the ordered filter-chain stats payload.
 *
 * @returns Normalized filter stats data.
 */
export async function fetchFilterStats(): Promise<FilterStatsData> {
  const payload = await apiJson<BackendFilterStatsPayload>("/api/filter-stats");
  return {
    byFilterReason: payload.by_filter_reason,
  };
}

/**
 * Fetch one page of blog catalog records for the homepage/admin listings.
 *
 * @param query Optional catalog query parameters.
 * @returns Normalized catalog page payload.
 */
export async function fetchBlogsCatalog(query: BlogCatalogQuery = {}): Promise<BlogCatalogPage> {
  const params = new URLSearchParams();
  if (query.page) {
    params.set("page", String(query.page));
  }
  if (query.pageSize) {
    params.set("page_size", String(query.pageSize));
  }
  if (query.q) {
    params.set("q", query.q);
  }
  if (query.sort) {
    params.set("sort", query.sort);
  }
  if (query.site) {
    params.set("site", query.site);
  }
  if (query.url) {
    params.set("url", query.url);
  }
  if (query.status) {
    params.set("status", query.status);
  }
  if (query.statuses) {
    params.set("statuses", query.statuses);
  }
  if (query.hasTitle !== undefined) {
    params.set("has_title", String(query.hasTitle));
  }
  if (query.hasIcon !== undefined) {
    params.set("has_icon", String(query.hasIcon));
  }
  if (query.minConnections !== undefined) {
    params.set("min_connections", String(query.minConnections));
  }
  const payload = await apiJson<BackendCatalogPayload>(`/api/blogs/catalog?${params.toString()}`);
  return {
    items: payload.items.map(toBlogCatalogItem),
    page: payload.page,
    pageSize: payload.page_size,
    totalItems: payload.total_items,
    totalPages: payload.total_pages,
    hasNext: payload.has_next,
    hasPrev: payload.has_prev,
    sort: payload.sort,
  };
}

/**
 * Submit one ingestion request when a searched blog is missing.
 *
 * @param data User-provided URL and email pair.
 * @returns Created ingestion request summary.
 */
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

/**
 * Fetch the protected runtime status summary.
 *
 * @param adminToken Bearer token used for the protected endpoint.
 * @returns Normalized runtime status.
 */
export async function fetchAdminRuntimeStatus(adminToken: string): Promise<AdminRuntimeStatus> {
  const payload = await apiJson<BackendRuntimePayload>("/api/admin/runtime/status", {
    headers: adminHeaders(adminToken),
  });
  return toRuntimePayload(payload);
}

/**
 * Fetch the protected current runtime worker payload.
 *
 * @param adminToken Bearer token used for the protected endpoint.
 * @returns Normalized current runtime payload.
 */
export async function fetchAdminRuntimeCurrent(adminToken: string): Promise<AdminRuntimeCurrent> {
  const payload = await apiJson<BackendRuntimePayload>("/api/admin/runtime/current", {
    headers: adminHeaders(adminToken),
  });
  const normalized = toRuntimePayload(payload);
  return {
    runnerStatus: normalized.runnerStatus,
    activeRunId: normalized.activeRunId,
    workerCount: normalized.workerCount,
    activeWorkers: normalized.activeWorkers,
    currentBlogId: normalized.currentBlogId,
    currentUrl: normalized.currentUrl,
    currentStage: normalized.currentStage,
    elapsedSeconds: normalized.elapsedSeconds,
  };
}

/**
 * Fetch the latest dedup scan summary when available.
 *
 * @param adminToken Bearer token used for the protected endpoint.
 * @returns Normalized dedup summary or null when no run exists.
 */
export async function fetchAdminDedupLatest(adminToken: string): Promise<AdminDedupSummary | null> {
  try {
    const payload = await apiJson<BackendDedupSummary>("/api/admin/blog-dedup-scans/latest", {
      headers: adminHeaders(adminToken),
    });
    return {
      id: payload.id,
      status: payload.status,
      totalCount: payload.total_count,
      scannedCount: payload.scanned_count,
      removedCount: payload.removed_count,
      keptCount: payload.kept_count,
      createdAt: payload.created_at,
      updatedAt: payload.updated_at,
    };
  } catch {
    return null;
  }
}

export async function fetchAdminUrlRefilterLatest(adminToken: string): Promise<AdminUrlRefilterRun | null> {
  try {
    const payload = await apiJson<BackendUrlRefilterRun>("/api/admin/url-refilter-runs/latest", {
      headers: adminHeaders(adminToken),
    });
    return {
      id: payload.id,
      status: payload.status,
      filterChainVersion: payload.filter_chain_version,
      crawlerWasRunning: payload.crawler_was_running,
      backupPath: payload.backup_path,
      totalCount: payload.total_count,
      scannedCount: payload.scanned_count,
      unchangedCount: payload.unchanged_count,
      activatedCount: payload.activated_count,
      deactivatedCount: payload.deactivated_count,
      retaggedCount: payload.retagged_count,
      lastRawUrlId: payload.last_raw_url_id,
      startedAt: payload.started_at,
      completedAt: payload.completed_at,
      errorMessage: payload.error_message,
      createdAt: payload.created_at,
      updatedAt: payload.updated_at,
    };
  } catch {
    return null;
  }
}

export async function fetchAdminUrlRefilterEvents(
  adminToken: string,
  runId: number,
): Promise<AdminUrlRefilterRunEvent[]> {
  const payload = await apiJson<BackendUrlRefilterRunEvent[]>(`/api/admin/url-refilter-runs/${runId}/events`, {
    headers: adminHeaders(adminToken),
  });
  return payload.map((event) => ({
    id: event.id,
    runId: event.run_id,
    message: event.message,
    createdAt: event.created_at,
  }));
}

/**
 * Trigger seed import from the admin crawl bootstrap endpoint.
 *
 * @param adminToken Bearer token used for the protected endpoint.
 * @returns Raw admin response payload.
 */
export async function postAdminBootstrap(adminToken: string): Promise<unknown> {
  return apiJson("/api/admin/crawl/bootstrap", {
    method: "POST",
    headers: adminHeaders(adminToken),
  });
}

/**
 * Start the background crawler runtime.
 *
 * @param adminToken Bearer token used for the protected endpoint.
 * @returns Raw admin response payload.
 */
export async function postAdminRuntimeStart(adminToken: string): Promise<unknown> {
  return apiJson("/api/admin/runtime/start", {
    method: "POST",
    headers: adminHeaders(adminToken),
  });
}

/**
 * Request the background crawler runtime to stop.
 *
 * @param adminToken Bearer token used for the protected endpoint.
 * @returns Raw admin response payload.
 */
export async function postAdminRuntimeStop(adminToken: string): Promise<unknown> {
  return apiJson("/api/admin/runtime/stop", {
    method: "POST",
    headers: adminHeaders(adminToken),
  });
}

/**
 * Run one synchronous crawl batch.
 *
 * @param adminToken Bearer token used for the protected endpoint.
 * @param maxNodes Maximum number of blogs to process in the batch.
 * @returns Raw admin response payload.
 */
export async function postAdminRunBatch(adminToken: string, maxNodes: number): Promise<unknown> {
  return apiJson("/api/admin/runtime/run-batch", {
    method: "POST",
    headers: adminHeaders(adminToken),
    body: JSON.stringify({
      max_nodes: maxNodes,
    }),
  });
}

/**
 * Reset crawler persistence data through the admin maintenance endpoint.
 *
 * @param adminToken Bearer token used for the protected endpoint.
 * @returns Raw admin response payload.
 */
export async function postAdminResetDatabase(adminToken: string): Promise<unknown> {
  return apiJson("/api/admin/database/reset", {
    method: "POST",
    headers: adminHeaders(adminToken),
  });
}

export async function postAdminRunUrlRefilter(adminToken: string): Promise<unknown> {
  return apiJson("/api/admin/url-refilter-runs", {
    method: "POST",
    headers: adminHeaders(adminToken),
  });
}
