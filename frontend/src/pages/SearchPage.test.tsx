import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { SearchPage } from "./SearchPage";
import { useSearch } from "../lib/hooks";

vi.mock("../lib/hooks", () => ({
  useSearch: vi.fn(),
}));

const mockedUseSearch = vi.mocked(useSearch);

function renderSearchPage(initialEntry = "/search?q=friend") {
  const router = createMemoryRouter([{ path: "/search", element: <SearchPage /> }], {
    initialEntries: [initialEntry],
  });

  render(<RouterProvider router={router} />);
  return router;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedUseSearch.mockReturnValue({
    data: {
      query: "friend",
      kind: "all",
      limit: 10,
      blogs: [
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
          last_crawled_at: null,
          created_at: "2026-03-29T00:00:00Z",
          updated_at: "2026-03-29T00:00:00Z",
          incoming_count: 1,
          outgoing_count: 2,
          connection_count: 3,
          activity_at: "2026-03-29T00:00:00Z",
          identity_complete: true,
        },
      ],
      edges: [
        {
          id: 2,
          from_blog_id: 1,
          to_blog_id: 3,
          link_url_raw: "https://beta.example/blogroll",
          link_text: "Friend Link",
          discovered_at: "2026-03-29T00:00:00Z",
          from_blog: {
            id: 1,
            domain: "alpha.example",
            title: "Alpha Blog",
            icon_url: "https://alpha.example/favicon.ico",
          },
          to_blog: {
            id: 3,
            domain: "beta.example",
            title: "Beta Blog",
            icon_url: "https://beta.example/favicon.ico",
          },
        },
      ],
      logs: [],
    },
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useSearch>);
});

afterEach(() => {
  cleanup();
});

test("reads q from the URL and only searches after explicit submit", async () => {
  const router = renderSearchPage();

  const input = screen.getByRole("searchbox", { name: "关键词" });
  expect(input).toHaveValue("friend");
  expect(mockedUseSearch).toHaveBeenLastCalledWith("friend", {
    enabled: true,
    kind: "all",
    limit: 10,
  });

  await userEvent.clear(input);
  await userEvent.type(input, "graph");
  expect(mockedUseSearch).toHaveBeenLastCalledWith("friend", {
    enabled: true,
    kind: "all",
    limit: 10,
  });

  await userEvent.click(screen.getByRole("button", { name: "搜索" }));

  await waitFor(() => {
    expect(router.state.location.search).toBe("?q=graph&kind=all&limit=10");
    expect(mockedUseSearch).toHaveBeenLastCalledWith("graph", {
      enabled: true,
      kind: "all",
      limit: 10,
    });
  });
});

test("normalizes unsupported kind and oversized limit from the URL", () => {
  renderSearchPage("/search?q=friend&kind=unexpected&limit=999");

  expect(mockedUseSearch).toHaveBeenLastCalledWith("friend", {
    enabled: true,
    kind: "all",
    limit: 50,
  });
  expect(screen.getByDisplayValue("50")).toBeInTheDocument();
});

test("renders blogs as the primary result block with detail links", () => {
  renderSearchPage();

  expect(screen.getByRole("heading", { name: "博客结果" })).toBeInTheDocument();
  expect(screen.getByRole("img", { name: "Alpha Blog icon" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /前往 Beta Blog/i })).toHaveAttribute("href", "/blogs/3");
  expect(screen.getByRole("heading", { name: "关系线索" })).toBeInTheDocument();
});

test("renders an error state when the search request fails", () => {
  mockedUseSearch.mockReturnValue({
    data: undefined,
    isLoading: false,
    error: new Error("503 Service Unavailable"),
  } as unknown as ReturnType<typeof useSearch>);

  renderSearchPage();

  expect(screen.getByText(/请求失败：503 Service Unavailable/i)).toBeInTheDocument();
});
