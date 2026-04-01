import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ApiError } from "../lib/api";
import { BlogDetailPage } from "./BlogDetailPage";
import { useBlogDetailView } from "../lib/hooks";

vi.mock("../lib/hooks", () => ({
  useBlogDetailView: vi.fn(),
}));

const mockedUseBlogDetailView = vi.mocked(useBlogDetailView);

function renderDetailPage(initialEntry = "/blogs/1") {
  const router = createMemoryRouter([{ path: "/blogs/:blogId", element: <BlogDetailPage /> }], {
    initialEntries: [initialEntry],
  });

  render(<RouterProvider router={router} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedUseBlogDetailView.mockReturnValue({
    blog: {
      id: 1,
      url: "https://alpha.example",
      normalized_url: "https://alpha.example",
      domain: "alpha.example",
      status_code: 200,
      crawl_status: "FINISHED",
      friend_links_count: 4,
      source_blog_id: null,
      last_crawled_at: null,
      created_at: "2026-03-29T00:00:00Z",
      updated_at: "2026-03-29T00:00:00Z",
      outgoing_edges: [
        {
          id: 10,
          from_blog_id: 1,
          to_blog_id: 2,
          link_url_raw: "https://beta.example",
          link_text: "Beta",
          discovered_at: "2026-03-29T00:00:00Z",
        },
      ],
    },
    incomingEdges: [
      {
        id: 11,
        from_blog_id: 3,
        to_blog_id: 1,
        link_url_raw: "https://alpha.example",
        link_text: "Alpha",
        discovered_at: "2026-03-29T00:00:00Z",
        neighborBlog: {
          id: 3,
          url: "https://gamma.example",
          normalized_url: "https://gamma.example",
          domain: "gamma.example",
          status_code: 200,
          crawl_status: "FINISHED",
          friend_links_count: 2,
          source_blog_id: 1,
          last_crawled_at: null,
          created_at: "2026-03-29T00:00:00Z",
          updated_at: "2026-03-29T00:00:00Z",
        },
      },
    ],
    outgoingEdges: [
      {
        id: 10,
        from_blog_id: 1,
        to_blog_id: 2,
        link_url_raw: "https://beta.example",
        link_text: "Beta",
        discovered_at: "2026-03-29T00:00:00Z",
        neighborBlog: {
          id: 2,
          url: "https://beta.example",
          normalized_url: "https://beta.example",
          domain: "beta.example",
          status_code: 200,
          crawl_status: "FINISHED",
          friend_links_count: 1,
          source_blog_id: 1,
          last_crawled_at: null,
          created_at: "2026-03-29T00:00:00Z",
          updated_at: "2026-03-29T00:00:00Z",
        },
      },
    ],
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useBlogDetailView>);
});

afterEach(() => {
  cleanup();
});

test("renders blog detail with outgoing and incoming relationship links", () => {
  renderDetailPage();

  expect(mockedUseBlogDetailView).toHaveBeenCalledWith(1);
  expect(screen.getByRole("heading", { name: "alpha.example" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "gamma.example" })).toHaveAttribute("href", "/blogs/3");
  expect(screen.getByRole("link", { name: "beta.example" })).toHaveAttribute("href", "/blogs/2");
});

test("shows an invalid-state message for malformed blog ids", () => {
  renderDetailPage("/blogs/not-a-number");

  expect(screen.getByText("博客详情不可用")).toBeInTheDocument();
  expect(mockedUseBlogDetailView).toHaveBeenCalledWith(null);
});

test("shows a not-found state when the backend returns 404", () => {
  mockedUseBlogDetailView.mockReturnValue({
    blog: null,
    incomingEdges: [],
    outgoingEdges: [],
    isLoading: false,
    error: new ApiError(404, "Not Found"),
  } as unknown as ReturnType<typeof useBlogDetailView>);

  renderDetailPage();

  expect(screen.getByText("博客不存在")).toBeInTheDocument();
  expect(screen.getByText(/系统中没有找到 ID 为 1 的博客记录/)).toBeInTheDocument();
});
