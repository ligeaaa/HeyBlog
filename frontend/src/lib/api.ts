export type RuntimeStatus = {
  runner_status: string;
  maintenance_in_progress?: boolean;
  active_run_id: string | null;
  worker_count: number;
  active_workers: number;
  current_worker_id: string | null;
  current_blog_id: number | null;
  current_url: string | null;
  current_stage: string | null;
  task_started_at: string | null;
  elapsed_seconds: number | null;
  last_started_at: string | null;
  last_stopped_at: string | null;
  last_error: string | null;
  last_result: Record<string, unknown> | null;
  workers: RuntimeWorkerStatus[];
};

export type RuntimeWorkerStatus = {
  worker_id: string;
  worker_index: number;
  status: string;
  current_blog_id: number | null;
  current_url: string | null;
  current_stage: string | null;
  task_started_at: string | null;
  last_transition_at: string | null;
  last_completed_at: string | null;
  last_error: string | null;
  processed: number;
  discovered: number;
  failed: number;
  elapsed_seconds: number | null;
};

export type BlogRecord = {
  id: number;
  url: string;
  normalized_url: string;
  identity_key?: string;
  identity_reason_codes?: string[];
  identity_ruleset_version?: string;
  domain: string;
  email?: string | null;
  title: string | null;
  icon_url: string | null;
  status_code: number | null;
  crawl_status: string;
  friend_links_count: number;
  last_crawled_at: string | null;
  created_at: string;
  updated_at: string;
  incoming_count: number;
  outgoing_count: number;
  connection_count: number;
  activity_at: string | null;
  identity_complete: boolean;
};

export type LogRecord = {
  id: number;
  blog_id: number | null;
  stage: string;
  result: string;
  message: string;
  created_at: string;
};

export type EdgeRecord = {
  id: number;
  from_blog_id: number;
  to_blog_id: number;
  link_url_raw: string;
  link_text: string | null;
  discovered_at: string;
};

export type BlogNeighborSummary = Pick<BlogRecord, "id" | "domain" | "title" | "icon_url">;

export type BlogRelationRecord = EdgeRecord & {
  neighbor_blog: BlogNeighborSummary | null;
};

export type BlogRecommendationRecord = {
  blog: BlogRecord;
  reason: "mutual_connection";
  mutual_connection_count: number;
  via_blogs: BlogNeighborSummary[];
};

export type SearchEdgeRecord = EdgeRecord & {
  from_blog: BlogNeighborSummary | null;
  to_blog: BlogNeighborSummary | null;
};

export type GraphPayload = {
  nodes: BlogRecord[];
  edges: EdgeRecord[];
};

export type GraphNodeRecord = BlogRecord & {
  x?: number;
  y?: number;
  degree?: number;
  incoming_count?: number;
  outgoing_count?: number;
  priority_score?: number;
  component_id?: string;
};

export type GraphViewMeta = {
  strategy: string;
  limit: number;
  sample_mode: "off" | "count" | "percent";
  sample_value: number | null;
  sample_seed: number;
  sampled: boolean;
  focus_node_id: number | null;
  hops: number | null;
  has_stable_positions: boolean;
  snapshot_version: string | null;
  generated_at: string | null;
  source: string;
  total_nodes: number;
  total_edges: number;
  available_nodes: number;
  available_edges: number;
  selected_nodes: number;
  selected_edges: number;
  graph_fingerprint?: string | null;
};

export type GraphViewPayload = {
  nodes: GraphNodeRecord[];
  edges: EdgeRecord[];
  meta: GraphViewMeta;
};

export type GraphSnapshotManifest = {
  version: string;
  generated_at: string;
  source: string;
  has_stable_positions: boolean;
  total_nodes: number;
  total_edges: number;
  available_nodes: number;
  available_edges: number;
  graph_fingerprint?: string | null;
  file: string;
};

export type GraphSnapshotPayload = GraphViewPayload & {
  version: string;
  generated_at: string;
};

export type BlogDetailPayload = BlogRecord & {
  incoming_edges: BlogRelationRecord[];
  outgoing_edges: BlogRelationRecord[];
  recommended_blogs: BlogRecommendationRecord[];
};

export type BlogCatalogFilters = {
  q: string | null;
  site: string | null;
  url: string | null;
  status: string | null;
  sort: string;
  has_title: boolean | null;
  has_icon: boolean | null;
  min_connections: number;
};

export type BlogCatalogPagePayload = {
  items: BlogRecord[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
  filters: BlogCatalogFilters;
  sort: string;
};

export type BlogLabelTagRecord = {
  id: number;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
};

export type BlogLabelAssignmentRecord = BlogLabelTagRecord & {
  labeled_at: string | null;
};

export type BlogLabelingCandidateRecord = BlogRecord & {
  labels: BlogLabelAssignmentRecord[];
  label_slugs: string[];
  last_labeled_at: string | null;
  is_labeled: boolean;
};

export type BlogLabelingFilters = {
  q: string | null;
  label: string | null;
  labeled: boolean | null;
  sort: string;
};

export type BlogLabelingPagePayload = {
  items: BlogLabelingCandidateRecord[];
  available_tags: BlogLabelTagRecord[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
  filters: BlogLabelingFilters;
  sort: string;
};

export type ReplaceBlogLinkLabelsPayload = {
  blog_id: number;
  labels: BlogLabelAssignmentRecord[];
  label_slugs: string[];
  last_labeled_at: string | null;
  is_labeled: boolean;
};

export type CreateBlogLabelTagPayload = BlogLabelTagRecord;

export type SearchPayload = {
  query: string;
  kind: "all" | "blogs" | "relations";
  limit: number;
  blogs: BlogRecord[];
  edges: SearchEdgeRecord[];
  logs: LogRecord[];
};

export type IngestionRequestPayload = {
  id: number;
  request_id: number;
  requested_url: string;
  normalized_url: string;
  identity_key?: string;
  identity_reason_codes?: string[];
  identity_ruleset_version?: string;
  email: string;
  status: string;
  priority: number;
  seed_blog_id: number | null;
  matched_blog_id: number | null;
  blog_id: number | null;
  request_token: string;
  expires_at: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  seed_blog: BlogRecord | null;
  matched_blog: BlogRecord | null;
  blog: BlogRecord | null;
};

export type CreateIngestionRequestResponse =
  | {
      status: "DEDUPED_EXISTING";
      blog_id: number;
      matched_blog_id: number;
      request_id: null;
      request_token: null;
      blog: BlogRecord;
    }
  | (IngestionRequestPayload & {
      status: "QUEUED" | "CRAWLING_SEED" | "COMPLETED" | "FAILED" | "RECEIVED";
    });

export type StatusPayload = {
  is_running: boolean;
  pending_tasks: number;
  processing_tasks: number;
  finished_tasks: number;
  failed_tasks: number;
  total_blogs: number;
  total_edges: number;
};

export type StatsPayload = {
  total_blogs: number;
  total_edges: number;
  average_friend_links: number;
  status_counts: Record<string, number>;
  pending_tasks: number;
  processing_tasks: number;
  failed_tasks: number;
  finished_tasks: number;
};

export type ResetDatabasePayload = {
  ok: boolean;
  blogs_deleted: number;
  edges_deleted: number;
  logs_deleted: number;
  ingestion_requests_deleted?: number;
  blog_link_labels_deleted?: number;
  blog_label_tags_deleted?: number;
  search_reindexed: boolean;
  search: Record<string, unknown> | null;
  search_error?: string;
};

export type BlogDedupScanRunPayload = {
  id: number;
  status: string;
  ruleset_version: string;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number;
  total_count: number;
  scanned_count: number;
  removed_count: number;
  kept_count: number;
  crawler_was_running: boolean;
  crawler_restart_attempted: boolean;
  crawler_restart_succeeded: boolean;
  search_reindexed: boolean;
  error_message: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type BlogDedupScanRunItemPayload = {
  id: number;
  run_id: number;
  survivor_blog_id: number | null;
  removed_blog_id: number | null;
  survivor_identity_key: string;
  removed_url: string;
  removed_normalized_url: string;
  removed_domain: string;
  reason_code: string;
  reason_codes: string[];
  survivor_selection_basis: string;
  created_at: string | null;
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) {
        message = String(payload.detail);
      }
    } catch {
      // Keep the default status-based message when the body is not JSON.
    }
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}

function withQuery(path: string, params: Record<string, string | number | boolean | null | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value == null) {
      continue;
    }
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

export const api = {
  blogs: () => request<BlogRecord[]>("/api/blogs"),
  blogCatalog: (params: {
    page: number;
    pageSize: number;
    q?: string | null;
    site?: string | null;
    url?: string | null;
    status?: string | null;
    sort?: string;
    hasTitle?: boolean | null;
    hasIcon?: boolean | null;
    minConnections?: number | null;
  }) =>
    request<BlogCatalogPagePayload>(
      withQuery("/api/blogs/catalog", {
        page: params.page,
        page_size: params.pageSize,
        q: params.q,
        site: params.site,
        url: params.url,
        status: params.status,
        sort: params.sort,
        has_title: params.hasTitle,
        has_icon: params.hasIcon,
        min_connections: params.minConnections,
      }),
    ),
  blogLabelingCandidates: (params: {
    page: number;
    pageSize: number;
    q?: string | null;
    label?: string | null;
    labeled?: boolean | null;
    sort?: string;
  }) =>
    request<BlogLabelingPagePayload>(
      withQuery("/api/blog-labeling/candidates", {
        page: params.page,
        page_size: params.pageSize,
        q: params.q,
        label: params.label,
        labeled: params.labeled,
        sort: params.sort,
      }),
    ),
  blogLabelTags: () => request<BlogLabelTagRecord[]>("/api/blog-labeling/tags"),
  createBlogLabelTag: (params: { name: string }) =>
    request<CreateBlogLabelTagPayload>("/api/blog-labeling/tags", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: params.name }),
    }),
  replaceBlogLinkLabels: (params: { blogId: number; tagIds: number[] }) =>
    request<ReplaceBlogLinkLabelsPayload>(`/api/blog-labeling/labels/${params.blogId}`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        tag_ids: params.tagIds,
      }),
    }),
  blog: (blogId: number | string) => request<BlogDetailPayload>(`/api/blogs/${blogId}`),
  edges: () => request<EdgeRecord[]>("/api/edges"),
  status: () => request<StatusPayload>("/api/status"),
  stats: () => request<StatsPayload>("/api/stats"),
  graph: () => request<GraphPayload>("/api/graph"),
  graphView: (params: {
    strategy: string;
    limit: number;
    sampleMode: "off" | "count" | "percent";
    sampleValue: number | null;
    sampleSeed: number;
  }) =>
    request<GraphViewPayload>(
      withQuery("/api/graph/views/core", {
        strategy: params.strategy,
        limit: params.limit,
        sample_mode: params.sampleMode,
        sample_value: params.sampleValue,
        sample_seed: params.sampleSeed,
      }),
    ),
  graphNeighbors: (blogId: number | string, params: { hops: number; limit: number }) =>
    request<GraphViewPayload>(
      withQuery(`/api/graph/nodes/${blogId}/neighbors`, {
        hops: params.hops,
        limit: params.limit,
      }),
    ),
  latestGraphSnapshot: () => request<GraphSnapshotManifest>("/api/graph/snapshots/latest"),
  graphSnapshot: (version: string) => request<GraphSnapshotPayload>(`/api/graph/snapshots/${version}`),
  search: (params: { query: string; kind?: "all" | "blogs" | "relations"; limit?: number }) =>
    request<SearchPayload>(
      withQuery("/api/search", {
        q: params.query,
        kind: params.kind ?? "all",
        limit: params.limit ?? 10,
      }),
    ),
  createIngestionRequest: (params: { homepageUrl: string; email: string }) =>
    request<CreateIngestionRequestResponse>("/api/ingestion-requests", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        homepage_url: params.homepageUrl,
        email: params.email,
      }),
    }),
  ingestionRequest: (requestId: number, requestToken: string) =>
    request<IngestionRequestPayload>(
      withQuery(`/api/ingestion-requests/${requestId}`, {
        request_token: requestToken,
      }),
    ),
  runtimeStatus: () => request<RuntimeStatus>("/api/runtime/status"),
  runtimeCurrent: () => request<RuntimeStatus>("/api/runtime/current"),
  startCrawler: () => request<RuntimeStatus>("/api/runtime/start", { method: "POST" }),
  stopCrawler: () => request<RuntimeStatus>("/api/runtime/stop", { method: "POST" }),
  runBatch: (maxNodes: number) =>
    request<Record<string, unknown>>("/api/runtime/run-batch", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ max_nodes: maxNodes }),
    }),
  bootstrap: () => request<Record<string, unknown>>("/api/crawl/bootstrap", { method: "POST" }),
  resetDatabase: () => request<ResetDatabasePayload>("/api/database/reset", { method: "POST" }),
  runBlogDedupScan: () =>
    request<BlogDedupScanRunPayload>("/api/admin/blog-dedup-scans", { method: "POST" }),
  latestBlogDedupScanRun: () =>
    request<BlogDedupScanRunPayload>("/api/admin/blog-dedup-scans/latest"),
  blogDedupScanRun: (runId: number) =>
    request<BlogDedupScanRunPayload>(`/api/admin/blog-dedup-scans/${runId}`),
  blogDedupScanRunItems: (runId: number) =>
    request<BlogDedupScanRunItemPayload[]>(`/api/admin/blog-dedup-scans/${runId}/items`),
};
