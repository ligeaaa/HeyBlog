import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { SearchPage } from "./SearchPage";
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

function renderSearchPage(initialEntry = "/search?q=https%3A%2F%2Ffriend.example%2F") {
  const router = createMemoryRouter([{ path: "/search", element: <SearchPage /> }], {
    initialEntries: [initialEntry],
  });
  render(<RouterProvider router={router} />);
  return router;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedUseBlogCatalog.mockReturnValue({
    data: {
      items: [],
      page: 1,
      page_size: 50,
      total_items: 0,
      total_pages: 0,
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
  } as unknown as ReturnType<typeof useBlogCatalog>);
  mockedUsePriorityIngestionRequests.mockReturnValue({
    data: [],
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

test("treats legacy /search?q=... as lookup input in the unified page", () => {
  renderSearchPage();

  expect(mockedUseBlogLookup).toHaveBeenLastCalledWith("https://friend.example/", { enabled: true });
  expect(mockedUseSearch).toHaveBeenLastCalledWith("", {
    enabled: false,
    kind: "relations",
    limit: 10,
  });
  expect(screen.getByText(/旧 \/search 链接现在会落到同一统一页面/i)).toBeInTheDocument();
});

test("keeps /search?q=...&kind=relations as the expanded compatibility panel", () => {
  mockedUseSearch.mockReturnValue({
    data: {
      query: "friend",
      kind: "relations",
      limit: 20,
      blogs: [],
      edges: [
        {
          id: 1,
          from_blog_id: 1,
          to_blog_id: 2,
          link_url_raw: "https://friend.example/blogroll",
          link_text: "Friend Link",
          discovered_at: "2026-04-08T00:00:00Z",
          from_blog: { id: 1, domain: "alpha.example", title: "Alpha", icon_url: null },
          to_blog: { id: 2, domain: "friend.example", title: "Friend", icon_url: null },
        },
      ],
      logs: [],
    },
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useSearch>);

  renderSearchPage("/search?q=friend&kind=relations&limit=20");

  expect(mockedUseBlogLookup).toHaveBeenLastCalledWith("", { enabled: false });
  expect(mockedUseSearch).toHaveBeenLastCalledWith("friend", {
    enabled: true,
    kind: "relations",
    limit: 20,
  });
  expect(screen.getByText("Friend Link")).toBeInTheDocument();
});
