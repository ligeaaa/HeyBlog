import type {
  AdminDedupSummary,
  AdminBlogLabelCounts,
  AdminBlogLabelingCandidate,
  AdminBlogLabelingPage,
  AdminBlogLabelParquetStatus,
  AdminRequeueFailedBlogsResult,
  AdminBlogLabelTag,
  AdminRuntimeCurrent,
  AdminRuntimeStatus,
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
  AuthSession,
  UserLabelSelection,
  UserProfile,
} from "../types/graph";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  /**
   * Capture one failed API response with the backend detail payload intact.
   *
   * @param status HTTP response status.
   * @param detail Backend error detail payload, when available.
   */
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" && detail ? detail : `api_error_${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

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
  rule_drops?: Record<string, number>;
  success_sources?: Record<string, number>;
  funnel?: {
    raw: number;
    after_rules: number;
    model_rejected: number;
    success: number;
    blogs: number;
  };
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

interface BackendUserProfile {
  id: number;
  email: string;
  display_name: string;
  created_at: string | null;
  updated_at: string | null;
}

interface BackendAuthSession {
  token: string;
  expires_at: string | null;
  user: BackendUserProfile;
}

interface BackendUserLabelSelection {
  id: number;
  normalized_url: string;
  label_id: number;
  label: string;
  label_name: string;
  created_at: string | null;
  updated_at: string | null;
  blog: BackendGraphNode | null;
}

interface BackendUserLabelStats {
  label_count: number;
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

interface BackendBlogLabelTag {
  id: number;
  name: string;
  slug: string;
  count?: number;
  created_at: string | null;
  updated_at: string | null;
}

interface BackendBlogLabelAssignment extends BackendBlogLabelTag {
  labeled_at: string | null;
}

interface BackendBlogLabelingCandidate extends BackendGraphNode {
  labels: BackendBlogLabelAssignment[];
  label_slugs: string[];
  last_labeled_at: string | null;
  is_labeled: boolean;
}

interface BackendBlogLabelState {
  label_id: Record<string, number>;
  labels: BackendBlogLabelAssignment[];
  label_slugs: string[];
  last_labeled_at: string | null;
  is_labeled: boolean;
}

interface BackendBlogLabelingPage {
  items: BackendBlogLabelingCandidate[];
  available_tags: BackendBlogLabelTag[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
  sort: string;
}

interface BackendBlogLabelParquetStatus {
  path: string;
  filename: string;
  exists: boolean;
  saved_count: number;
  total_labeled: number;
  missing_count: number;
  batch_size: number;
  rewritten: boolean;
  message: string;
  updated_at: string | null;
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

interface BlogLabelingQuery {
  page?: number;
  pageSize?: number;
  q?: string;
  label?: string;
  labeled?: boolean;
  sort?: string;
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
 * Convert one backend blog label tag into the frontend admin tag shape.
 *
 * @param tag Raw backend label tag payload.
 * @returns Normalized admin label tag.
 */
function toAdminBlogLabelTag(tag: BackendBlogLabelTag): AdminBlogLabelTag {
  return {
    id: tag.id,
    name: tag.name,
    slug: tag.slug,
    createdAt: tag.created_at ?? "",
    updatedAt: tag.updated_at ?? "",
  };
}

/**
 * Convert one backend labeling candidate into the frontend admin candidate shape.
 *
 * @param candidate Raw backend labeling candidate payload.
 * @returns Normalized admin labeling candidate.
 */
function toAdminBlogLabelingCandidate(
  candidate: BackendBlogLabelingCandidate,
): AdminBlogLabelingCandidate {
  return {
    ...toBlogCatalogItem(candidate),
    labels: candidate.labels.map((label) => ({
      ...toAdminBlogLabelTag(label),
      labeledAt: label.labeled_at ?? "",
    })),
    labelSlugs: candidate.label_slugs,
    lastLabeledAt: candidate.last_labeled_at,
    isLabeled: candidate.is_labeled,
  };
}

/**
 * Convert one backend parquet status payload into frontend field casing.
 *
 * @param status Raw backend parquet status payload.
 * @returns Normalized parquet status used by the admin workbench.
 */
function toAdminBlogLabelParquetStatus(status: BackendBlogLabelParquetStatus): AdminBlogLabelParquetStatus {
  return {
    path: status.path,
    filename: status.filename,
    exists: status.exists,
    savedCount: status.saved_count,
    totalLabeled: status.total_labeled,
    missingCount: status.missing_count,
    batchSize: status.batch_size,
    rewritten: status.rewritten,
    message: status.message,
    updatedAt: status.updated_at,
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
    let detail: unknown = null;
    try {
      const payload = await response.json();
      detail = (payload as { detail?: unknown }).detail ?? payload;
    } catch {
      detail = await response.text().catch(() => null);
    }
    throw new ApiError(response.status, detail);
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

function authHeaders(token: string): HeadersInit {
  return {
    authorization: `Bearer ${token.trim()}`,
  };
}

function toUserProfile(user: BackendUserProfile): UserProfile {
  return {
    id: user.id,
    email: user.email,
    displayName: user.display_name,
    createdAt: user.created_at,
    updatedAt: user.updated_at,
  };
}

function toAuthSession(session: BackendAuthSession): AuthSession {
  return {
    token: session.token,
    expiresAt: session.expires_at,
    user: toUserProfile(session.user),
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
    strategy: "seed",
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
  const fallbackRaw = payload.by_filter_reason.raw ?? 0;
  const fallbackSuccess = payload.by_filter_reason.success ?? 0;
  const fallbackBlogs = payload.by_filter_reason.blogs ?? 0;
  const derivedRuleDrops: Record<string, number> = {};
  let previousRemaining = fallbackRaw;
  let fallbackAfterRules = fallbackRaw;
  for (const [status, remaining] of Object.entries(payload.by_filter_reason)) {
    if (!status.startsWith("rule:")) {
      continue;
    }
    derivedRuleDrops[status] = Math.max(previousRemaining - remaining, 0);
    previousRemaining = remaining;
    fallbackAfterRules = remaining;
  }
  const hasExplicitSources = payload.success_sources !== undefined;
  return {
    byFilterReason: payload.by_filter_reason,
    ruleDrops: payload.rule_drops ?? derivedRuleDrops,
    successSources: payload.success_sources ?? {},
    funnel: {
      raw: payload.funnel?.raw ?? fallbackRaw,
      afterRules: payload.funnel?.after_rules ?? fallbackAfterRules,
      modelRejected: payload.funnel?.model_rejected ?? 0,
      success: payload.funnel?.success ?? fallbackSuccess,
      blogs: payload.funnel?.blogs ?? fallbackBlogs,
    },
    ...(hasExplicitSources
      ? {}
      : {
          successSources: {
            unknown: fallbackSuccess,
          },
        }),
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
 * Submit one user seed URL so it can be accepted and queued for crawling.
 *
 * @param data User-provided complete blog URL.
 * @returns Accepted blog seed summary.
 */
export async function submitUserSeed(data: { url: string }): Promise<{ status: string; blogId: number }> {
  if (!data.url.trim()) {
    throw new Error("url_required");
  }
  let payload: { status: string; blog_id: number };
  try {
    payload = await apiJson<{ status: string; blog_id: number }>("/api/blogs/user-seeds", {
      method: "POST",
      body: JSON.stringify({
        homepage_url: data.url.trim(),
      }),
    });
  } catch (error) {
    throw new Error(describeUserSeedError(error));
  }
  return {
    status: payload.status,
    blogId: payload.blog_id,
  };
}

function describeUserSeedError(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return error instanceof Error ? error.message : "提交失败：未知错误";
  }
  const detail = typeof error.detail === "string" ? error.detail : "";
  const ruleReason = USER_SEED_RULE_REASON_MESSAGES[detail];
  if (ruleReason) {
    return `规则过滤未通过：${ruleReason}（${detail}）`;
  }
  if (detail === "Unsupported homepage URL") {
    return "URL 无法识别：请输入完整的 http 或 https 博客首页链接。";
  }
  if (detail) {
    return `提交失败：${detail}`;
  }
  return `提交失败：接口返回 ${error.status}`;
}

const USER_SEED_RULE_REASON_MESSAGES: Record<string, string> = {
  "rule:duplicate_url": "该 URL 已经存在于发现记录中",
  "rule:non_http_scheme": "链接不是 http 或 https 协议",
  "rule:same_domain": "链接与来源域名相同",
  "rule:exact_url_blocked": "链接命中精确 URL 黑名单",
  "rule:prefix_blocked": "链接命中 URL 前缀黑名单",
  "rule:platform_blocked": "域名属于已屏蔽的平台站点",
  "rule:domain_blocked": "域名命中自定义屏蔽列表",
  "rule:blocked_tld": "域名后缀被屏蔽",
  "rule:non_root_path": "链接不是博客首页根路径",
  "rule:non_root_location": "链接包含查询参数或锚点",
  "rule:asset_suffix": "链接指向静态资源文件",
  "rule:blocked_path": "链接路径属于登录、搜索、RSS、管理页等非博客首页",
};

export async function registerUser(data: { email: string; password: string }): Promise<AuthSession> {
  const payload = await apiJson<BackendAuthSession>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({
      email: data.email.trim(),
      password: data.password,
    }),
  });
  return toAuthSession(payload);
}

export async function loginUser(data: { email: string; password: string }): Promise<AuthSession> {
  const payload = await apiJson<BackendAuthSession>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({
      email: data.email.trim(),
      password: data.password,
    }),
  });
  return toAuthSession(payload);
}

export async function fetchCurrentUser(token: string): Promise<UserProfile> {
  const payload = await apiJson<BackendUserProfile>("/api/auth/me", {
    headers: authHeaders(token),
  });
  return toUserProfile(payload);
}

export async function logoutUser(token: string): Promise<void> {
  await apiJson<{ ok: boolean }>("/api/auth/logout", {
    method: "POST",
    headers: authHeaders(token),
  });
}

export async function fetchMyLabelSelections(token: string, limit = 50): Promise<UserLabelSelection[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  const payload = await apiJson<BackendUserLabelSelection[]>(`/api/me/label-selections?${params.toString()}`, {
    headers: authHeaders(token),
  });
  return payload.map((selection) => ({
    id: selection.id,
    normalizedUrl: selection.normalized_url,
    labelId: selection.label_id,
    label: selection.label,
    labelName: selection.label_name,
    createdAt: selection.created_at,
    updatedAt: selection.updated_at,
    blog: selection.blog ? toBlogCatalogItem(selection.blog) : null,
  }));
}

export async function fetchMyLabelStats(token: string): Promise<{ labelCount: number }> {
  const payload = await apiJson<BackendUserLabelStats>("/api/me/label-stats", {
    headers: authHeaders(token),
  });
  return { labelCount: payload.label_count };
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

/**
 * Fetch one page of protected blog labeling candidates.
 *
 * @param adminToken Bearer token used for the protected endpoint.
 * @param query Optional labeling query parameters.
 * @returns Normalized labeling page payload.
 */
export async function fetchAdminBlogLabelingCandidates(
  adminToken: string,
  query: BlogLabelingQuery = {},
): Promise<AdminBlogLabelingPage> {
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
  if (query.label) {
    params.set("label", query.label);
  }
  if (query.labeled !== undefined) {
    params.set("labeled", String(query.labeled));
  }
  if (query.sort) {
    params.set("sort", query.sort);
  }
  const payload = await apiJson<BackendBlogLabelingPage>(
    `/api/admin/blog-labeling/candidates?${params.toString()}`,
    {
      headers: adminHeaders(adminToken),
    },
  );
  return {
    items: payload.items.map(toAdminBlogLabelingCandidate),
    availableTags: payload.available_tags.map(toAdminBlogLabelTag),
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
 * Create or return an existing protected blog label tag.
 *
 * @param adminToken Bearer token used for the protected endpoint.
 * @param name Label name to create.
 * @returns Normalized admin label tag.
 */
export async function postAdminBlogLabelTag(adminToken: string, name: string): Promise<AdminBlogLabelTag> {
  const payload = await apiJson<BackendBlogLabelTag>("/api/admin/blog-labeling/tags", {
    method: "POST",
    headers: adminHeaders(adminToken),
    body: JSON.stringify({ name }),
  });
  return toAdminBlogLabelTag(payload);
}

/**
 * Replace one protected blog candidate's labels.
 *
 * @param adminToken Bearer token used for the protected endpoint.
 * @param blogId Target blog business id.
 * @param tagIds Complete replacement tag id list.
 * @returns Updated label state for the target blog.
 */
export async function putAdminBlogLabels(
  adminToken: string,
  blogId: number,
  tagIds: number[],
  labelId?: Record<string, number>,
  title?: string | null,
): Promise<{ labelSlugs: string[]; isLabeled: boolean; lastLabeledAt: string | null }> {
  const body =
    labelId === undefined
      ? { tag_ids: tagIds, title: title?.trim() || undefined }
      : { label_id: labelId, title: title?.trim() || undefined };
  const payload = await apiJson<{
    label_slugs: string[];
    is_labeled: boolean;
    last_labeled_at: string | null;
  }>(`/api/admin/blog-labeling/labels/${blogId}`, {
    method: "PUT",
    headers: adminHeaders(adminToken),
    body: JSON.stringify(body),
  });
  return {
    labelSlugs: payload.label_slugs,
    isLabeled: payload.is_labeled,
    lastLabeledAt: payload.last_labeled_at,
  };
}

/**
 * Increment one public random-blog label counter for a catalog card.
 *
 * @param blogId Public/business blog ID.
 * @param label Label slug to select.
 * @param previousLabel Optional previous page-local label selection to decrement.
 * @returns Updated label state after persistence saves the vote.
 */
export async function postBlogUserLabel(
  blogId: number,
  label: string,
  previousLabel?: string,
  token?: string | null,
): Promise<{ labelId: Record<string, number>; labelSlugs: string[]; lastLabeledAt: string | null }> {
  const payload = await apiJson<BackendBlogLabelState>(`/api/blogs/${blogId}/user-labels`, {
    method: "POST",
    headers: token ? authHeaders(token) : undefined,
    body: JSON.stringify({ label, previous_label: previousLabel }),
  });
  return {
    labelId: payload.label_id,
    labelSlugs: payload.label_slugs,
    lastLabeledAt: payload.last_labeled_at,
  };
}

/**
 * Fetch one candidate URL title for temporary labeling display.
 *
 * @param adminToken Bearer token used for the protected endpoint.
 * @param url Candidate URL to inspect.
 * @returns Extracted title, or null when no title is present.
 */
export async function fetchAdminBlogLabelTitlePreview(
  adminToken: string,
  url: string,
): Promise<string | null> {
  const payload = await apiJson<{ title: string | null }>("/api/admin/blog-labeling/title-preview", {
    method: "POST",
    headers: adminHeaders(adminToken),
    body: JSON.stringify({ url }),
  });
  return payload.title?.trim() || null;
}

/**
 * Fetch label counts for every current label slug.
 *
 * @param adminToken Bearer token used for the protected endpoint.
 * @returns Count summary grouped by label slug.
 */
export async function fetchAdminBlogLabelCounts(adminToken: string): Promise<AdminBlogLabelCounts> {
  const payload = await apiJson<{ total_labeled: number; by_label: Record<string, number> }>(
    "/api/admin/blog-labeling/counts",
    {
      headers: adminHeaders(adminToken),
    },
  );
  return {
    totalLabeled: payload.total_labeled,
    byLabel: payload.by_label,
  };
}

/**
 * Fetch the current parquet export status.
 *
 * @param adminToken Bearer token used for the protected endpoint.
 * @returns Normalized parquet status payload.
 */
export async function fetchAdminBlogLabelParquetStatus(adminToken: string): Promise<AdminBlogLabelParquetStatus> {
  const payload = await apiJson<BackendBlogLabelParquetStatus>("/api/admin/blog-labeling/parquet-status", {
    headers: adminHeaders(adminToken),
  });
  return toAdminBlogLabelParquetStatus(payload);
}

/**
 * Check and fill missing labeled rows in the parquet export.
 *
 * @param adminToken Bearer token used for the protected endpoint.
 * @returns Normalized parquet status after the sync.
 */
export async function postAdminBlogLabelParquetSync(adminToken: string): Promise<AdminBlogLabelParquetStatus> {
  const payload = await apiJson<BackendBlogLabelParquetStatus>("/api/admin/blog-labeling/parquet-sync", {
    method: "POST",
    headers: adminHeaders(adminToken),
  });
  return toAdminBlogLabelParquetStatus(payload);
}

/**
 * Rebuild the parquet export from all current labeled rows.
 *
 * @param adminToken Bearer token used for the protected endpoint.
 * @returns Normalized parquet status after the rebuild.
 */
export async function postAdminBlogLabelParquetRebuild(adminToken: string): Promise<AdminBlogLabelParquetStatus> {
  const payload = await apiJson<BackendBlogLabelParquetStatus>("/api/admin/blog-labeling/parquet-rebuild", {
    method: "POST",
    headers: adminHeaders(adminToken),
  });
  return toAdminBlogLabelParquetStatus(payload);
}

/**
 * Download the current parquet export through the browser.
 *
 * @param adminToken Bearer token used for the protected endpoint.
 * @returns Promise resolved after the browser download has been started.
 */
export async function downloadAdminBlogLabelParquet(adminToken: string): Promise<void> {
  const response = await fetch("/api/admin/blog-labeling/parquet-export", {
    headers: adminHeaders(adminToken),
  });
  if (!response.ok) {
    throw new Error(`api_error_${response.status}`);
  }
  const blob = await response.blob();
  const contentDisposition = response.headers.get("content-disposition") ?? "";
  const filenameMatch = /filename="?(?<filename>[^";]+)"?/i.exec(contentDisposition);
  const filename = filenameMatch?.groups?.filename ?? "blog-label-training.parquet";
  const objectUrl = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(objectUrl);
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
 * Requeue every failed blog so the crawler can retry it.
 *
 * @param adminToken Bearer token used for the protected endpoint.
 * @returns Number of failed blogs moved back to the waiting queue.
 */
export async function postAdminRequeueFailedBlogs(adminToken: string): Promise<AdminRequeueFailedBlogsResult> {
  return apiJson<AdminRequeueFailedBlogsResult>("/api/admin/blogs/requeue-failed", {
    method: "POST",
    headers: adminHeaders(adminToken),
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
