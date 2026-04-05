import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BlogCatalogPagePayload,
  BlogLabelTagRecord,
  BlogLabelingPagePayload,
  CreateBlogLabelTagPayload,
  BlogNeighborSummary,
  EdgeRecord,
  ReplaceBlogLinkLabelsPayload,
} from "./api";
import { api } from "./api";

type QueryTuning = {
  enabled?: boolean;
  refetchInterval?: number | false;
  staleTime?: number;
};

export type RelatedEdge = EdgeRecord & {
  neighborBlog: BlogNeighborSummary | null;
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
  sort?: string;
  hasTitle?: boolean | null;
  hasIcon?: boolean | null;
  minConnections?: number | null;
  enabled?: boolean;
};

export type BlogLabelingOptions = {
  page: number;
  pageSize?: number;
  q?: string | null;
  label?: string | null;
  labeled?: boolean | null;
  sort?: string;
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
    sort: options.sort ?? "id_desc",
    hasTitle: options.hasTitle ?? null,
    hasIcon: options.hasIcon ?? null,
    minConnections: options.minConnections ?? null,
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
        sort: queryOptions.sort,
        hasTitle: queryOptions.hasTitle,
        hasIcon: queryOptions.hasIcon,
        minConnections: queryOptions.minConnections,
      }),
    enabled: options.enabled ?? true,
    staleTime: 30000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    placeholderData: (previousData: BlogCatalogPagePayload | undefined) => previousData,
  });
}

export function useBlogLabelingCandidates(options: BlogLabelingOptions) {
  const pageSize = options.pageSize ?? 50;
  const queryOptions = {
    page: options.page,
    pageSize,
    q: options.q ?? null,
    label: options.label ?? null,
    labeled: options.labeled ?? null,
    sort: options.sort ?? "id_desc",
  };

  return useQuery({
    queryKey: ["blog-labeling-candidates", queryOptions],
    queryFn: () =>
      api.blogLabelingCandidates({
        page: queryOptions.page,
        pageSize: queryOptions.pageSize,
        q: queryOptions.q,
        label: queryOptions.label,
        labeled: queryOptions.labeled,
        sort: queryOptions.sort,
      }),
    enabled: options.enabled ?? true,
    staleTime: 30000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    placeholderData: (previousData: BlogLabelingPagePayload | undefined) => previousData,
  });
}

export function useCreateBlogLabelTag() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: { name: string }) => api.createBlogLabelTag(params),
    onSuccess: async (payload: CreateBlogLabelTagPayload) => {
      queryClient.setQueriesData(
        { queryKey: ["blog-labeling-candidates"] },
        (current: BlogLabelingPagePayload | undefined) => {
          if (!current) {
            return current;
          }
          return {
            ...current,
            available_tags: [...current.available_tags, payload].sort((left, right) =>
              left.name.localeCompare(right.name, "en"),
            ),
          };
        },
      );
      await queryClient.invalidateQueries({ queryKey: ["blog-labeling-candidates"] });
    },
  });
}

export function useReplaceBlogLinkLabels() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: { blogId: number; tagIds: number[] }) => api.replaceBlogLinkLabels(params),
    onSuccess: (payload: ReplaceBlogLinkLabelsPayload) => {
      queryClient.setQueriesData(
        { queryKey: ["blog-labeling-candidates"] },
        (current: BlogLabelingPagePayload | undefined) => {
          if (!current) {
            return current;
          }
          return {
            ...current,
            items: current.items.map((item) =>
              item.id === payload.blog_id
                ? {
                    ...item,
                    labels: payload.labels,
                    label_slugs: payload.label_slugs,
                    last_labeled_at: payload.last_labeled_at,
                    is_labeled: payload.is_labeled,
                  }
                : item,
            ),
          };
        },
      );
      void queryClient.invalidateQueries({ queryKey: ["blog-labeling-candidates"] });
    },
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

export type GraphNeighborOptions = {
  blogId: number | null;
  hops: number;
  limit: number;
  enabled?: boolean;
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

export function useGraphNeighbors(options: GraphNeighborOptions) {
  return useQuery({
    queryKey: ["graph-neighbors", options.blogId, options.hops, options.limit],
    queryFn: () =>
      api.graphNeighbors(options.blogId as number, {
        hops: options.hops,
        limit: options.limit,
      }),
    enabled: (options.enabled ?? true) && options.blogId != null,
    staleTime: 60000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
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

export function useSearch(
  query: string,
  options: {
    kind?: "all" | "blogs" | "relations";
    limit?: number;
    enabled?: boolean;
  } = {},
) {
  return useQuery({
    queryKey: ["search", query, options.kind ?? "all", options.limit ?? 10],
    queryFn: () =>
      api.search({
        query,
        kind: options.kind ?? "all",
        limit: options.limit ?? 10,
      }),
    enabled: options.enabled ?? true,
    staleTime: 60000,
  });
}

export function useCreateIngestionRequest() {
  return useMutation({
    mutationFn: (params: { homepageUrl: string; email: string }) => api.createIngestionRequest(params),
  });
}

export function useIngestionRequestStatus(
  requestId: number | null,
  requestToken: string | null,
  options: QueryTuning = {},
) {
  return useQuery({
    queryKey: ["ingestion-request", requestId, requestToken],
    queryFn: () => api.ingestionRequest(requestId as number, requestToken as string),
    enabled: (options.enabled ?? true) && requestId != null && requestToken != null,
    staleTime: options.staleTime ?? 0,
    refetchInterval: options.refetchInterval ?? 2500,
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
  const outgoingEdges: RelatedEdge[] = (detail.data?.outgoing_edges ?? []).map((edge) => ({
    ...edge,
    neighborBlog: edge.neighbor_blog ?? null,
  }));
  const incomingEdges: RelatedEdge[] = (detail.data?.incoming_edges ?? []).map((edge) => ({
    ...edge,
    neighborBlog: edge.neighbor_blog ?? null,
  }));

  const error = detail.error ?? null;
  const isLoading = detail.isLoading;

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

export function useRuntimeWorkers() {
  return useQuery({
    queryKey: ["runtime-workers"],
    queryFn: api.runtimeStatus,
    refetchInterval: 1500,
    select: (payload) => payload.workers,
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
      queryClient.invalidateQueries({ queryKey: ["runtime-workers"] }),
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
