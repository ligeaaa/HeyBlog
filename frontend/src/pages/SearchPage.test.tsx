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
      blogs: [
        {
          id: 1,
          url: "https://alpha.example",
          normalized_url: "https://alpha.example",
          domain: "alpha.example",
          status_code: 200,
          crawl_status: "FINISHED",
          friend_links_count: 3,
          depth: 0,
          source_blog_id: null,
          last_crawled_at: null,
          created_at: "2026-03-29T00:00:00Z",
          updated_at: "2026-03-29T00:00:00Z",
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
        },
      ],
      logs: [
        {
          id: 3,
          blog_id: 1,
          stage: "crawl",
          result: "success",
          message: "Crawled alpha.example",
          created_at: "2026-03-29T00:00:00Z",
        },
      ],
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
  expect(mockedUseSearch).toHaveBeenLastCalledWith("friend", true);

  await userEvent.clear(input);
  await userEvent.type(input, "graph");
  expect(mockedUseSearch).toHaveBeenLastCalledWith("friend", true);

  await userEvent.click(screen.getByRole("button", { name: "搜索" }));

  await waitFor(() => {
    expect(router.state.location.search).toBe("?q=graph");
    expect(mockedUseSearch).toHaveBeenLastCalledWith("graph", true);
  });
});

test("renders blogs as the primary result block with detail links", () => {
  renderSearchPage();

  expect(screen.getByRole("heading", { name: "博客结果" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "alpha.example" })).toHaveAttribute("href", "/blogs/1");
  expect(screen.getByRole("heading", { name: "边线索" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "日志命中" })).toBeInTheDocument();
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
