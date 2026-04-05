import { describe, expect, test, vi } from "vitest";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { useBlogCatalog, useBlogDetailView, useGraphNeighbors } from "./hooks";

vi.mock("@tanstack/react-query", () => ({
  useMutation: vi.fn(),
  useQuery: vi.fn(),
  useQueryClient: vi.fn(),
}));

vi.mock("./api", () => ({
  api: {
    blogCatalog: vi.fn(),
    blog: vi.fn(),
    graphNeighbors: vi.fn(),
  },
}));

describe("useBlogCatalog", () => {
  test("uses a non-polling query configuration", async () => {
    vi.mocked(useQuery).mockReturnValue({} as never);
    vi.mocked(api.blogCatalog).mockResolvedValue({} as never);

    useBlogCatalog({
      page: 2,
      site: "alpha",
      status: "FINISHED",
    });

    expect(useQuery).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: [
          "blog-catalog",
          {
            page: 2,
            pageSize: 50,
            q: null,
            site: "alpha",
            url: null,
            status: "FINISHED",
            sort: "id_desc",
            hasTitle: null,
            hasIcon: null,
            minConnections: null,
          },
        ],
        enabled: true,
        staleTime: 30000,
        refetchInterval: false,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
      }),
    );

    const queryConfig = vi.mocked(useQuery).mock.calls[0][0] as unknown as {
      queryFn: (context?: unknown) => Promise<unknown>;
    };
    await queryConfig.queryFn({} as never);

    expect(api.blogCatalog).toHaveBeenCalledWith({
      page: 2,
      pageSize: 50,
      q: null,
      site: "alpha",
      url: null,
      status: "FINISHED",
      sort: "id_desc",
      hasTitle: null,
      hasIcon: null,
      minConnections: null,
    });
  });
});

describe("useBlogDetailView", () => {
  test("maps backend-provided relationship summaries without extra queries", async () => {
    vi.clearAllMocks();
    vi.mocked(useQuery).mockReturnValue({
      data: {
        id: 5,
        domain: "alpha.example",
        recommended_blogs: [],
        incoming_edges: [
          {
            id: 12,
            from_blog_id: 3,
            to_blog_id: 5,
            link_url_raw: "https://alpha.example",
            link_text: "Alpha",
            discovered_at: "2026-03-31T00:00:00Z",
            neighbor_blog: {
              id: 3,
              domain: "gamma.example",
              title: "Gamma",
              icon_url: "https://gamma.example/favicon.ico",
            },
          },
        ],
        outgoing_edges: [
          {
            id: 13,
            from_blog_id: 5,
            to_blog_id: 8,
            link_url_raw: "https://beta.example",
            link_text: "Beta",
            discovered_at: "2026-03-31T00:00:00Z",
            neighbor_blog: {
              id: 8,
              domain: "beta.example",
              title: "Beta",
              icon_url: "https://beta.example/favicon.ico",
            },
          },
        ],
      },
      isLoading: false,
      error: null,
    } as never);
    vi.mocked(api.blog).mockResolvedValue({} as never);

    const result = useBlogDetailView(5);

    expect(useQuery).toHaveBeenCalledTimes(1);
    expect(useQuery).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: ["blog-detail", 5],
        enabled: true,
        staleTime: 60000,
      }),
    );

    const queryConfig = vi.mocked(useQuery).mock.calls[0][0] as unknown as {
      queryFn: () => Promise<unknown>;
    };
    await queryConfig.queryFn();

    expect(api.blog).toHaveBeenCalledWith(5);
    expect(result.incomingEdges[0].neighborBlog?.domain).toBe("gamma.example");
    expect(result.outgoingEdges[0].neighborBlog?.domain).toBe("beta.example");
  });
});

describe("useGraphNeighbors", () => {
  test("uses a focused non-polling graph neighbor query", async () => {
    vi.clearAllMocks();
    vi.mocked(useQuery).mockReturnValue({} as never);
    vi.mocked(api.graphNeighbors).mockResolvedValue({} as never);

    useGraphNeighbors({
      blogId: 5,
      hops: 2,
      limit: 90,
    });

    expect(useQuery).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: ["graph-neighbors", 5, 2, 90],
        enabled: true,
        staleTime: 60000,
        refetchInterval: false,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
      }),
    );

    const queryConfig = vi.mocked(useQuery).mock.calls[0][0] as unknown as {
      queryFn: () => Promise<unknown>;
    };
    await queryConfig.queryFn();

    expect(api.graphNeighbors).toHaveBeenCalledWith(5, {
      hops: 2,
      limit: 90,
    });
  });
});
