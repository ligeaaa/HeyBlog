import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { BlogsPage } from "./BlogsPage";
import {
  useBlogCatalog,
  useBlogLookup,
  useCreateIngestionRequest,
  useIngestionRequestStatus,
  usePriorityIngestionRequests,
  useSearch,
} from "../lib/hooks";

vi.mock("../lib/hooks", () => ({
  BLOG_CRAWL_STATUS_OPTIONS: ["WAITING", "PROCESSING", "FINISHED", "FAILED"],
  useBlogCatalog: vi.fn(),
  usePriorityIngestionRequests: vi.fn(),
  useBlogLookup: vi.fn(),
  useSearch: vi.fn(),
  useCreateIngestionRequest: vi.fn(),
  useIngestionRequestStatus: vi.fn(),
}));

const mockedUseBlogCatalog = vi.mocked(useBlogCatalog);
const mockedUsePriorityIngestionRequests = vi.mocked(usePriorityIngestionRequests);
const mockedUseBlogLookup = vi.mocked(useBlogLookup);
const mockedUseSearch = vi.mocked(useSearch);
const mockedUseCreateIngestionRequest = vi.mocked(useCreateIngestionRequest);
const mockedUseIngestionRequestStatus = vi.mocked(useIngestionRequestStatus);

function buildCatalogResult() {
  return {
    data: {
      items: [
        {
          id: 2,
          url: "https://beta.example/",
          normalized_url: "https://beta.example/",
          domain: "beta.example",
          title: "Beta Blog",
          icon_url: "https://beta.example/favicon.ico",
          status_code: 200,
          crawl_status: "WAITING",
          friend_links_count: 0,
          last_crawled_at: null,
          created_at: "2026-04-08T00:00:00Z",
          updated_at: "2026-04-08T00:00:00Z",
          incoming_count: 0,
          outgoing_count: 0,
          connection_count: 0,
          activity_at: "2026-04-08T00:00:00Z",
          identity_complete: true,
          email: null,
        },
      ],
      page: 1,
      page_size: 50,
      total_items: 1,
      total_pages: 1,
      has_next: false,
      has_prev: false,
      filters: {
        q: null,
        site: null,
        url: null,
        status: null,
        statuses: ["WAITING", "PROCESSING"],
        sort: "id_asc",
        has_title: null,
        has_icon: null,
        min_connections: 0,
      },
      sort: "id_asc",
    },
    isLoading: false,
    isFetching: false,
    error: null,
    refetch: vi.fn().mockResolvedValue(undefined),
  } as unknown as ReturnType<typeof useBlogCatalog>;
}

function renderBlogsPage(initialEntry = "/blogs") {
  const router = createMemoryRouter([{ path: "/blogs", element: <BlogsPage /> }], {
    initialEntries: [initialEntry],
  });
  render(<RouterProvider router={router} />);
  return router;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedUseBlogCatalog.mockReturnValue(buildCatalogResult());
  mockedUsePriorityIngestionRequests.mockReturnValue({
    data: [
      {
        request_id: 11,
        requested_url: "https://queued.example/",
        normalized_url: "https://queued.example/",
        status: "QUEUED",
        seed_blog_id: 3,
        matched_blog_id: null,
        blog_id: 3,
        error_message: null,
        created_at: "2026-04-08T00:00:00Z",
        updated_at: "2026-04-08T00:00:00Z",
        blog: {
          id: 3,
          url: "https://queued.example/",
          normalized_url: "https://queued.example/",
          domain: "queued.example",
          title: "Queued Blog",
          icon_url: null,
          status_code: null,
          crawl_status: "WAITING",
          friend_links_count: 0,
          last_crawled_at: null,
          created_at: "2026-04-08T00:00:00Z",
          updated_at: "2026-04-08T00:00:00Z",
          incoming_count: 0,
          outgoing_count: 0,
          connection_count: 0,
          activity_at: null,
          identity_complete: true,
          email: null,
        },
      },
    ],
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof usePriorityIngestionRequests>);
  mockedUseBlogLookup.mockReturnValue({
    data: undefined,
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useBlogLookup>);
  mockedUseSearch.mockReturnValue({
    data: { query: "", kind: "relations", limit: 10, blogs: [], edges: [], logs: [] },
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useSearch>);
  mockedUseCreateIngestionRequest.mockReturnValue({
    mutateAsync: vi.fn(),
    data: undefined,
    error: null,
    isPending: false,
  } as unknown as ReturnType<typeof useCreateIngestionRequest>);
  mockedUseIngestionRequestStatus.mockReturnValue({
    data: undefined,
    error: null,
    isLoading: false,
  } as unknown as ReturnType<typeof useIngestionRequestStatus>);
});

afterEach(() => {
  cleanup();
});

test("loads the unified queue view with frozen statuses and sort", () => {
  renderBlogsPage();

  expect(mockedUseBlogCatalog).toHaveBeenCalledWith({
    page: 1,
    pageSize: 50,
    statuses: ["WAITING", "PROCESSING"],
    sort: "id_asc",
  });
  expect(screen.getByRole("heading", { name: "当前博客状态" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "优先处理博客清单" })).toBeInTheDocument();
  expect(screen.getByText("请求状态：QUEUED")).toBeInTheDocument();
  expect(screen.getByText("https://queued.example/")).toBeInTheDocument();
});

test("submits lookup through the dedicated lookup query param", async () => {
  const user = userEvent.setup();
  const router = renderBlogsPage();

  await user.type(screen.getByRole("textbox", { name: "博客首页 URL" }), "https://alpha.example/");
  await user.click(screen.getByRole("button", { name: "检查是否已收录" }));

  await waitFor(() => {
    expect(router.state.location.search).toBe("?lookup=https%3A%2F%2Falpha.example%2F");
  });
  expect(mockedUseSearch).toHaveBeenLastCalledWith("", {
    enabled: false,
    kind: "relations",
    limit: 10,
  });
});

test("renders lookup hit results without showing the ingestion form", () => {
  mockedUseBlogLookup.mockReturnValue({
    data: {
      query_url: "https://alpha.example/",
      normalized_query_url: "https://alpha.example/",
      items: [
        {
          id: 1,
          url: "https://alpha.example/",
          normalized_url: "https://alpha.example/",
          domain: "alpha.example",
          title: "Alpha Blog",
          icon_url: "https://alpha.example/favicon.ico",
          status_code: 200,
          crawl_status: "FINISHED",
          friend_links_count: 1,
          last_crawled_at: null,
          created_at: "2026-04-08T00:00:00Z",
          updated_at: "2026-04-08T00:00:00Z",
          incoming_count: 0,
          outgoing_count: 0,
          connection_count: 1,
          activity_at: null,
          identity_complete: true,
          email: null,
        },
      ],
      total_matches: 1,
      match_reason: "identity_key",
    },
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useBlogLookup>);

  renderBlogsPage("/blogs?lookup=https%3A%2F%2Falpha.example%2F");

  expect(mockedUseBlogLookup).toHaveBeenLastCalledWith("https://alpha.example/", { enabled: true });
  expect(screen.getByText(/命中原因：identity_key/i)).toBeInTheDocument();
  expect(screen.queryByRole("textbox", { name: "联系邮箱" })).not.toBeInTheDocument();
});

test("opens the legacy relations compatibility panel when q/kind=relations is present", () => {
  mockedUseSearch.mockReturnValue({
    data: {
      query: "friend",
      kind: "relations",
      limit: 12,
      blogs: [],
      edges: [
        {
          id: 7,
          from_blog_id: 1,
          to_blog_id: 2,
          link_url_raw: "https://friend.example/blogroll",
          link_text: "Friend Link",
          discovered_at: "2026-04-08T00:00:00Z",
          from_blog: { id: 1, domain: "alpha.example", title: "Alpha Blog", icon_url: null },
          to_blog: { id: 2, domain: "friend.example", title: "Friend Blog", icon_url: null },
        },
      ],
      logs: [],
    },
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useSearch>);

  renderBlogsPage("/blogs?q=friend&kind=relations&limit=12");

  expect(mockedUseSearch).toHaveBeenLastCalledWith("friend", {
    enabled: true,
    kind: "relations",
    limit: 12,
  });
  expect(screen.getByRole("heading", { name: "高级关系线索搜索（兼容）" })).toBeInTheDocument();
  expect(screen.getByText("Friend Link")).toBeInTheDocument();
});
