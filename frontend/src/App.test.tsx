import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("@antv/g6", () => ({
  Graph: class {
    on() {}

    setOptions() {}

    setSize() {}

    updateNodeData() {}

    render() {
      return Promise.resolve();
    }

    draw() {
      return Promise.resolve();
    }

    destroy() {}
  },
}));

import App from "./App";

function makeCatalogItem(id: number, crawlStatus: string, title: string) {
  return {
    id,
    url: `https://${title.toLowerCase().replace(/\s+/g, "-")}.example.com/`,
    normalized_url: `https://${title.toLowerCase().replace(/\s+/g, "-")}.example.com/`,
    identity_key: `site:${title.toLowerCase().replace(/\s+/g, "-")}.example.com/`,
    identity_reason_codes: ["scheme_ignored"],
    identity_ruleset_version: "2026-04-07-v5",
    domain: `${title.toLowerCase().replace(/\s+/g, "-")}.example.com`,
    email: null,
    title,
    icon_url: null,
    status_code: crawlStatus === "FAILED" ? 500 : crawlStatus === "FINISHED" ? 200 : null,
    crawl_status: crawlStatus,
    friend_links_count: 0,
    last_crawled_at: crawlStatus === "FINISHED" ? `2026-04-16T${String(id).padStart(2, "0")}:00:00Z` : null,
    created_at: `2026-04-${String((id % 20) + 1).padStart(2, "0")}T10:00:00Z`,
    updated_at: `2026-04-${String((id % 20) + 1).padStart(2, "0")}T10:00:00Z`,
    incoming_count: 0,
    outgoing_count: 0,
    connection_count: 0,
    activity_at: crawlStatus === "FINISHED" ? `2026-04-${String((id % 20) + 1).padStart(2, "0")}T10:00:00Z` : null,
    identity_complete: crawlStatus === "FINISHED",
  };
}

function sortCatalogItems(items: Array<Record<string, unknown>>, sort: string) {
  const copied = [...items];
  if (sort === "id_desc") {
    copied.sort((left, right) => Number(right.id) - Number(left.id));
  } else if (sort === "id_asc") {
    copied.sort((left, right) => Number(left.id) - Number(right.id));
  } else if (sort === "random") {
    copied.sort((left, right) => Number(left.id) - Number(right.id));
    copied.reverse();
  }
  return copied;
}

const baseCatalogItems = [
  makeCatalogItem(1, "PROCESSING", "Processing Blog"),
  makeCatalogItem(2, "WAITING", "Waiting Blog"),
  makeCatalogItem(34, "WAITING", "Newest Waiting Blog"),
  makeCatalogItem(3, "FINISHED", "Finished Blog"),
  makeCatalogItem(4, "FAILED", "Failed Blog"),
  ...Array.from({ length: 28 }, (_, index) => makeCatalogItem(index + 5, "FINISHED", `Extra Blog ${index + 5}`)),
];

let catalogItems: Array<Record<string, unknown>> = baseCatalogItems;
let statusPayload = {
  is_running: true,
  pending_tasks: 3,
  processing_tasks: 1,
  finished_tasks: 30,
  failed_tasks: 1,
  total_blogs: 34,
  total_edges: 10,
};

beforeEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useFakeTimers({ shouldAdvanceTime: true });
  window.history.replaceState({}, "", "/");
  catalogItems = [...baseCatalogItems, makeCatalogItem(33, "PROCESSING", "Newest Processing Blog")];
  statusPayload = {
    is_running: true,
    pending_tasks: 3,
    processing_tasks: 2,
    finished_tasks: 30,
    failed_tasks: 1,
    total_blogs: 34,
    total_edges: 10,
  };

  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    if (url.pathname === "/api/blogs/catalog") {
      const page = Number(url.searchParams.get("page") || "1");
      const pageSize = Number(url.searchParams.get("page_size") || "30");
      const status = url.searchParams.get("status");
      const query = (url.searchParams.get("q") || "").trim().toLowerCase();
      const sort = url.searchParams.get("sort") || "id_asc";
      const filteredItems = sortCatalogItems(
        (status ? catalogItems.filter((item) => item.crawl_status === status) : catalogItems).filter((item) => {
          if (!query) {
            return true;
          }
          const title = String(item.title ?? "").toLowerCase();
          const blogUrl = String(item.url ?? "").toLowerCase();
          return title.includes(query) || blogUrl.includes(query);
        }),
        sort,
      );
      const offset = (page - 1) * pageSize;
      const pageItems = filteredItems.slice(offset, offset + pageSize);
      return new Response(
        JSON.stringify({
          items: pageItems,
          page,
          page_size: pageSize,
          total_items: filteredItems.length,
          total_pages: Math.ceil(filteredItems.length / pageSize),
          has_next: offset + pageSize < filteredItems.length,
          has_prev: page > 1,
          sort,
        }),
      );
    }
    if (url.pathname === "/api/status") {
      return new Response(JSON.stringify(statusPayload));
    }
    if (url.pathname === "/api/stats") {
      return new Response(JSON.stringify({ total_blogs: 34, total_edges: 10 }));
    }
    throw new Error(`Unhandled fetch: ${url.toString()}`);
  });

  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.useRealTimers();
});

test("renders paginated home cards, reloads from server for filters, and refreshes statuses by polling", async () => {
  render(<App />);

  await waitFor(() => {
    expect(screen.getByRole("heading", { name: /用统一首页浏览博客生态/i })).toBeInTheDocument();
  });

  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/api/blogs/catalog?page=1&page_size=30&sort=id_asc&status=PROCESSING"),
    expect.anything(),
  );
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/api/blogs/catalog?page=1&page_size=30&sort=id_asc&status=WAITING"),
    expect.anything(),
  );
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/api/blogs/catalog?page=1&page_size=30&sort=id_asc&status=FINISHED"),
    expect.anything(),
  );
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/api/blogs/catalog?page=1&page_size=30&sort=id_asc&status=FAILED"),
    expect.anything(),
  );
  expect(screen.getByText("Processing Blog")).toBeInTheDocument();
  expect(screen.getByText("Newest Processing Blog")).toBeInTheDocument();
  expect(screen.getByText("Waiting Blog")).toBeInTheDocument();
  expect(screen.getByText("当前显示第 1 / 2 页，本页 30 个，共 34 个博客")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "PROCESSING" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "FAILED" })).toBeInTheDocument();
  const titles = screen.getAllByRole("heading", { level: 3 }).map((node) => node.textContent);
  expect(titles.slice(0, 4)).toEqual(["Processing Blog", "Newest Processing Blog", "Waiting Blog", "Newest Waiting Blog"]);

  fireEvent.click(screen.getByRole("button", { name: "FAILED" }));

  await waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/blogs/catalog?page=1&page_size=30&sort=id_desc&status=FAILED"),
      expect.anything(),
    );
  });
  expect(screen.getByText("Failed Blog")).toBeInTheDocument();
  expect(screen.queryByText("Processing Blog")).not.toBeInTheDocument();
  expect(screen.getByText("当前显示第 1 / 1 页，本页 1 个，共 1 个博客")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "WAITING" }));

  await waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/blogs/catalog?page=1&page_size=30&sort=id_asc&status=WAITING"),
      expect.anything(),
    );
  });
  const waitingTitles = screen.getAllByRole("heading", { level: 3 }).map((node) => node.textContent);
  expect(waitingTitles.slice(0, 2)).toEqual(["Waiting Blog", "Newest Waiting Blog"]);

  fireEvent.click(screen.getByRole("button", { name: "ALL" }));

  await waitFor(() => {
    expect(screen.getByText("Processing Blog")).toBeInTheDocument();
  });

  fireEvent.click(screen.getByRole("button", { name: "下一页" }));

  await waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/blogs/catalog?page=1&page_size=60&sort=id_asc&status=PROCESSING"),
      expect.anything(),
    );
  });
  expect(screen.getByText("Failed Blog")).toBeInTheDocument();
  expect(screen.getByText("Extra Blog 32")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "PROCESSING" }));

  await waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/blogs/catalog?page=1&page_size=30&sort=id_desc&status=PROCESSING"),
      expect.anything(),
    );
  });
  expect(screen.getByText("Newest Processing Blog")).toBeInTheDocument();
  expect(screen.getByText("Processing Blog")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "ALL" }));

  await waitFor(() => {
    expect(screen.getByText("Waiting Blog")).toBeInTheDocument();
  });

  catalogItems = catalogItems.map((item) =>
    item.id === 1 ? { ...item, crawl_status: "FINISHED", status_code: 200, last_crawled_at: "2026-04-17T10:00:00Z" } : item,
  );
  statusPayload = {
    ...statusPayload,
    pending_tasks: 2,
    processing_tasks: 1,
    finished_tasks: 31,
  };

  await act(async () => {
    await vi.advanceTimersByTimeAsync(5000);
  });

  await waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/blogs/catalog?page=1&page_size=30&sort=id_asc&status=PROCESSING"),
      expect.anything(),
    );
  });

  fireEvent.click(screen.getByRole("button", { name: "PROCESSING" }));

  await waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/blogs/catalog?page=1&page_size=30&sort=id_desc&status=PROCESSING"),
      expect.anything(),
    );
  });
  expect(screen.getByText("Newest Processing Blog")).toBeInTheDocument();
  expect(screen.queryByText("Processing Blog")).not.toBeInTheDocument();

  fireEvent.change(screen.getByPlaceholderText(/输入 URL 或标题进行搜索/i), {
    target: { value: "Newest" },
  });
  fireEvent.click(screen.getByRole("button", { name: /搜索博客/i }));

  await waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/blogs/catalog?page=1&page_size=30&q=Newest&sort=id_desc&status=PROCESSING"),
      expect.anything(),
    );
  });
  expect(screen.getByText("Newest Processing Blog")).toBeInTheDocument();
  expect(screen.queryByText("Processing Blog")).not.toBeInTheDocument();
  expect(screen.queryByText("Newest Waiting Blog")).not.toBeInTheDocument();
  expect(screen.queryByText("Waiting Blog")).not.toBeInTheDocument();
  expect(screen.getByText("搜索词: Newest")).toBeInTheDocument();
});

test("adds a random blog route that loads nine finished cards and refreshes them on demand", async () => {
  window.history.replaceState({}, "", "/random");

  render(<App />);

  await waitFor(() => {
    expect(screen.getByRole("heading", { name: /随机发现 9 个已完成抓取的博客/i })).toBeInTheDocument();
  });

  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/api/blogs/catalog?page=1&page_size=9&sort=random&status=FINISHED"),
    expect.anything(),
  );
  expect(screen.getByText("当前展示 9 个随机博客卡片")).toBeInTheDocument();
  expect(screen.getByText("Extra Blog 32")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /刷新随机博客/i }));

  await waitFor(() => {
    const randomCalls = vi
      .mocked(fetch)
      .mock.calls.filter(([input]) =>
        String(input).includes("/api/blogs/catalog?page=1&page_size=9&sort=random&status=FINISHED"),
      );
    expect(randomCalls).toHaveLength(2);
  });
});
