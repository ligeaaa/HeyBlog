import { cleanup, render, screen, waitFor, act, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { BlogsPage } from "./BlogsPage";
import { useBlogCatalog } from "../lib/hooks";

vi.mock("../lib/hooks", () => ({
  BLOG_CRAWL_STATUS_OPTIONS: ["WAITING", "PROCESSING", "FINISHED", "FAILED"],
  useBlogCatalog: vi.fn(),
}));

const mockedUseBlogCatalog = vi.mocked(useBlogCatalog);

function buildCatalogData(page = 1, filters?: { q?: string | null; site?: string | null; url?: string | null; status?: string | null }) {
  return {
    items: [
      {
        id: 1,
        url: "https://alpha.example",
        normalized_url: "https://alpha.example",
        domain: "alpha.example",
        title: "Alpha Blog",
        icon_url: "https://alpha.example/favicon.ico",
        status_code: 200,
        crawl_status: "FINISHED",
        friend_links_count: 3,
        source_blog_id: null,
        last_crawled_at: null,
        created_at: "2026-03-31T00:00:00Z",
        updated_at: "2026-03-31T00:00:00Z",
      },
      {
        id: 2,
        url: "https://beta.example",
        normalized_url: "https://beta.example",
        domain: "beta.example",
        title: null,
        icon_url: null,
        status_code: 200,
        crawl_status: "WAITING",
        friend_links_count: 0,
        source_blog_id: 1,
        last_crawled_at: null,
        created_at: "2026-03-31T00:00:00Z",
        updated_at: "2026-03-31T00:00:00Z",
      },
    ],
    page,
    page_size: 50,
    total_items: 101,
    total_pages: 3,
    has_next: page < 3,
    has_prev: page > 1,
    filters: {
      q: filters?.q ?? null,
      site: filters?.site ?? null,
      url: filters?.url ?? null,
      status: filters?.status ?? null,
    },
    sort: "id_desc",
  };
}

function buildCatalogResult(overrides: Partial<ReturnType<typeof useBlogCatalog>> = {}) {
  return {
    data: buildCatalogData(),
    isLoading: false,
    isFetching: false,
    error: null,
    refetch: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  } as unknown as ReturnType<typeof useBlogCatalog>;
}

function createCatalogResult(options: {
  page: number;
  pageSize?: number;
  q?: string | null;
  site?: string | null;
  url?: string | null;
  status?: string | null;
}) {
  return {
    data: buildCatalogData(options.page, {
      q: options.q,
      site: options.site,
      url: options.url,
      status: options.status,
    }),
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
  mockedUseBlogCatalog.mockImplementation((options) =>
    createCatalogResult({
      page: options.page,
      pageSize: options.pageSize,
      q: options.q,
      site: options.site,
      url: options.url,
      status: options.status,
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

test("renders site identity from the catalog query", () => {
  renderBlogsPage("/blogs?page=2&site=alpha");

  expect(mockedUseBlogCatalog).toHaveBeenLastCalledWith({
    page: 2,
    pageSize: 50,
    q: null,
    site: "alpha",
    url: null,
    status: null,
  });
  expect(screen.getByRole("img", { name: "Alpha Blog icon" })).toBeInTheDocument();
  expect(screen.getByText("Alpha Blog")).toBeInTheDocument();
  expect(screen.getByText("alpha.example")).toBeInTheDocument();
  expect(screen.getByText("beta.example")).toBeInTheDocument();
  expect(screen.getByText(/共 101 条，当前第 2 \/ 3 页/i)).toBeInTheDocument();
});

test("debounces filter changes and resets paging in the URL", async () => {
  vi.useFakeTimers();
  const router = renderBlogsPage("/blogs?page=3&status=FAILED");

  const siteInput = screen.getByRole("searchbox", { name: "站点" });
  fireEvent.change(siteInput, { target: { value: "gamma" } });

  expect(router.state.location.search).toBe("?page=3&status=FAILED");

  await act(async () => {
    await vi.advanceTimersByTimeAsync(300);
  });

  expect(router.state.location.search).toBe("?site=gamma&status=FAILED");
  expect(mockedUseBlogCatalog).toHaveBeenLastCalledWith({
    page: 1,
    pageSize: 50,
    q: null,
    site: "gamma",
    url: null,
    status: "FAILED",
  });
});

test("supports paging controls and manual refresh", async () => {
  const refetch = vi.fn().mockResolvedValue(undefined);
  mockedUseBlogCatalog.mockImplementation((options) =>
    buildCatalogResult({
      data: buildCatalogData(options.page, {
        q: options.q,
        site: options.site,
        url: options.url,
        status: options.status,
      }),
      refetch,
    }),
  );
  const user = userEvent.setup();
  const router = renderBlogsPage();

  await user.click(screen.getByRole("button", { name: "下一页" }));

  await waitFor(() => {
    expect(router.state.location.search).toBe("?page=2");
    expect(mockedUseBlogCatalog).toHaveBeenLastCalledWith({
      page: 2,
      pageSize: 50,
      q: null,
      site: null,
      url: null,
      status: null,
    });
  });

  await user.click(screen.getByRole("button", { name: "手动刷新" }));
  expect(refetch).toHaveBeenCalled();
});

test("renders an error state when the catalog request fails", () => {
  mockedUseBlogCatalog.mockReturnValue(
    buildCatalogResult({
      data: undefined,
      error: new Error("503 Service Unavailable"),
    }),
  );

  renderBlogsPage();

  expect(screen.getByText(/加载失败：503 Service Unavailable/i)).toBeInTheDocument();
});
