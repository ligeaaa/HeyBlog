import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BlogCatalogPagePayload, BlogRecord, EdgeRecord } from "./api";
import { api } from "./api";

type QueryTuning = {
  enabled?: boolean;
  refetchInterval?: number | false;
  staleTime?: number;
};

export type RelatedEdge = EdgeRecord & {
  neighborBlog: BlogRecord | null;
};

export const BLOG_CRAWL_STATUS_OPTIONS = ["WAITING", "PROCESSING", "FINISHED", "FAILED"] as const;

export function useBlogs(options: QueryTuning = {}) {
  return useQuery({
    queryKey: ["blogs"],
    queryFn: api.blogs,
    enabled: options.enabled ?? true,
    refetchInterval: options.refetchInterval ?? 5000,
    staleTime: options.staleTime,
  });
}

export type BlogCatalogOptions = {
  page: number;
  pageSize?: number;
  q?: string | null;
  site?: string | null;
  url?: string | null;
  status?: string | null;
  enabled?: boolean;
};

export function useBlogCatalog(options: BlogCatalogOptions) {
  const pageSize = options.pageSize ?? 50;
  const queryOptions = {
    page: options.page,
    pageSize,
    q: options.q ?? null,
    site: options.site ?? null,
    url: options.url ?? null,
    status: options.status ?? null,
  };

  return useQuery({
    queryKey: ["blog-catalog", queryOptions],
    queryFn: () =>
      api.blogCatalog({
        page: queryOptions.page,
        pageSize: queryOptions.pageSize,
        q: queryOptions.q,
        site: queryOptions.site,
        url: queryOptions.url,
        status: queryOptions.status,
      }),
    enabled: options.enabled ?? true,
    staleTime: 30000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    placeholderData: (previousData: BlogCatalogPagePayload | undefined) => previousData,
  });
}

export function useStatus() {
  return useQuery({
    queryKey: ["status"],
    queryFn: api.status,
    refetchInterval: 4000,
  });
}

export function useStats() {
  return useQuery({
    queryKey: ["stats"],
    queryFn: api.stats,
    refetchInterval: 4000,
  });
}


export function useGraph() {
  return useGraphView({
    strategy: "degree",
    limit: 180,
    sampleMode: "off",
    sampleValue: null,
    sampleSeed: 7,
  });
}

export type GraphViewOptions = {
  strategy: string;
  limit: number;
  sampleMode: "off" | "count" | "percent";
  sampleValue: number | null;
  sampleSeed: number;
};

export function useGraphView(options: GraphViewOptions) {
  return useQuery({
    queryKey: ["graph-view", options],
    queryFn: () =>
      api.graphView({
        strategy: options.strategy,
        limit: options.limit,
        sampleMode: options.sampleMode,
        sampleValue: options.sampleValue,
        sampleSeed: options.sampleSeed,
      }),
    staleTime: 600000,
    refetchInterval: 600000,
  });
}

export function useEdges(options: QueryTuning = {}) {
  return useQuery({
    queryKey: ["edges"],
    queryFn: api.edges,
    enabled: options.enabled ?? true,
    refetchInterval: options.refetchInterval ?? false,
    staleTime: options.staleTime ?? 600000,
  });
}

export function useSearch(query: string, enabled = true) {
  return useQuery({
    queryKey: ["search", query],
    queryFn: () => api.search(query),
    enabled,
    staleTime: 60000,
  });
}

export function useBlogDetail(blogId: number | string | null) {
  return useQuery({
    queryKey: ["blog-detail", blogId],
    queryFn: () => api.blog(blogId as number | string),
    enabled: blogId != null,
    staleTime: 60000,
  });
}

export function useBlogDetailView(blogId: number | null) {
  const detail = useBlogDetail(blogId);
  const blogs = useBlogs({
    enabled: blogId != null,
    refetchInterval: false,
    staleTime: 600000,
  });
  const edges = useEdges({
    enabled: blogId != null,
    refetchInterval: false,
    staleTime: 600000,
  });

  const blogMap = new Map((blogs.data ?? []).map((blog) => [blog.id, blog]));
  const outgoingEdges: RelatedEdge[] = (detail.data?.outgoing_edges ?? []).map((edge) => ({
    ...edge,
    neighborBlog: blogMap.get(edge.to_blog_id) ?? null,
  }));
  const incomingEdges: RelatedEdge[] =
    blogId == null
      ? []
      : (edges.data ?? [])
          .filter((edge) => edge.to_blog_id === blogId)
          .map((edge) => ({
            ...edge,
            neighborBlog: blogMap.get(edge.from_blog_id) ?? null,
          }));

  const error = detail.error ?? blogs.error ?? edges.error ?? null;
  const isLoading = detail.isLoading || (!detail.error && (blogs.isLoading || edges.isLoading));

  return {
    blog: detail.data ?? null,
    incomingEdges,
    outgoingEdges,
    isLoading,
    error,
  };
}

export function useRuntimeStatus() {
  return useQuery({
    queryKey: ["runtime-status"],
    queryFn: api.runtimeStatus,
    refetchInterval: 1500,
  });
}

export function useRuntimeCurrent() {
  return useQuery({
    queryKey: ["runtime-current"],
    queryFn: api.runtimeCurrent,
    refetchInterval: 1500,
  });
}

export function useCrawlerActions() {
  const queryClient = useQueryClient();

  const invalidateAll = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["blogs"] }),
      queryClient.invalidateQueries({ queryKey: ["blog-catalog"] }),
      queryClient.invalidateQueries({ queryKey: ["edges"] }),
      queryClient.invalidateQueries({ queryKey: ["status"] }),
      queryClient.invalidateQueries({ queryKey: ["stats"] }),
      queryClient.invalidateQueries({ queryKey: ["graph"] }),
      queryClient.invalidateQueries({ queryKey: ["graph-view"] }),
      queryClient.invalidateQueries({ queryKey: ["runtime-status"] }),
      queryClient.invalidateQueries({ queryKey: ["runtime-current"] }),
    ]);
  };

  return {
    bootstrap: useMutation({
      mutationFn: api.bootstrap,
      onSuccess: invalidateAll,
    }),
    start: useMutation({
      mutationFn: api.startCrawler,
      onSuccess: invalidateAll,
    }),
    stop: useMutation({
      mutationFn: api.stopCrawler,
      onSuccess: invalidateAll,
    }),
    runBatch: useMutation({
      mutationFn: api.runBatch,
      onSuccess: invalidateAll,
    }),
    resetDatabase: useMutation({
      mutationFn: api.resetDatabase,
      onSuccess: invalidateAll,
    }),
  };
}
