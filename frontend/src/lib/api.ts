export type RuntimeStatus = {
  runner_status: string;
  active_run_id: string | null;
  current_blog_id: number | null;
  current_url: string | null;
  current_stage: string | null;
  last_started_at: string | null;
  last_stopped_at: string | null;
  last_error: string | null;
  last_result: Record<string, unknown> | null;
};

export type BlogRecord = {
  id: number;
  url: string;
  normalized_url: string;
  domain: string;
  status_code: number | null;
  crawl_status: string;
  friend_links_count: number;
  depth: number;
  source_blog_id: number | null;
  last_crawled_at: string | null;
  created_at: string;
  updated_at: string;
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

export type GraphPayload = {
  nodes: BlogRecord[];
  edges: EdgeRecord[];
};

export type BlogDetailPayload = BlogRecord & {
  outgoing_edges: EdgeRecord[];
};

export type SearchPayload = {
  query: string;
  blogs: BlogRecord[];
  edges: EdgeRecord[];
  logs: LogRecord[];
};

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
  max_depth: number;
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
  search_reindexed: boolean;
  search: Record<string, unknown> | null;
  search_error?: string;
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, statusText: string) {
    super(`${status} ${statusText}`);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    throw new ApiError(response.status, response.statusText);
  }
  return response.json() as Promise<T>;
}

export const api = {
  blogs: () => request<BlogRecord[]>("/api/blogs"),
  blog: (blogId: number | string) => request<BlogDetailPayload>(`/api/blogs/${blogId}`),
  edges: () => request<EdgeRecord[]>("/api/edges"),
  status: () => request<StatusPayload>("/api/status"),
  stats: () => request<StatsPayload>("/api/stats"),
  graph: () => request<GraphPayload>("/api/graph"),
  search: (query: string) => request<SearchPayload>(`/api/search?q=${encodeURIComponent(query)}`),
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
};
