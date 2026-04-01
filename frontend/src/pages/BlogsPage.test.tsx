import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { BlogsPage } from "./BlogsPage";
import { useBlogs } from "../lib/hooks";

vi.mock("../lib/hooks", () => ({
  useBlogs: vi.fn(),
}));

const mockedUseBlogs = vi.mocked(useBlogs);

beforeEach(() => {
  vi.clearAllMocks();
  mockedUseBlogs.mockReturnValue({
    data: [
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
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useBlogs>);
});

afterEach(() => {
  cleanup();
});

test("renders site identity with icon and title fallback", () => {
  render(
    <MemoryRouter>
      <BlogsPage />
    </MemoryRouter>,
  );

  expect(screen.getByRole("img", { name: "Alpha Blog icon" })).toBeInTheDocument();
  expect(screen.getByText("Alpha Blog")).toBeInTheDocument();
  expect(screen.getByText("alpha.example")).toBeInTheDocument();
  expect(screen.getByText("beta.example")).toBeInTheDocument();
});
