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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  blogs: () => request<BlogRecord[]>("/api/blogs"),
  status: () => request<StatusPayload>("/api/status"),
  stats: () => request<StatsPayload>("/api/stats"),
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
};
