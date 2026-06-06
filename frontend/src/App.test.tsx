import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const { forceGraphProps } = vi.hoisted(() => ({
  forceGraphProps: [] as Record<string, any>[],
}));

vi.mock("react-force-graph-3d", () => ({
  default: (props: Record<string, any>) => {
    forceGraphProps.push(props);
    return <div data-testid="force-graph-3d" />;
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

function makeDetailPayload(item: Record<string, unknown>) {
  const relatedBlog = makeCatalogItem(88, "FINISHED", "Related Blog");
  const recommendedBlog = makeCatalogItem(89, "FINISHED", "Recommended Blog");
  const viaBlog = makeCatalogItem(90, "FINISHED", "Mutual Blog");
  return {
    ...item,
    icon_url: `https://${String(item.domain)}/favicon.ico`,
    incoming_edges: [
      {
        id: "incoming-1",
        from_blog_id: relatedBlog.id,
        to_blog_id: item.id,
        link_text: "friend",
        link_url_raw: item.url,
        neighbor_blog: relatedBlog,
      },
    ],
    outgoing_edges: [
      {
        id: "outgoing-1",
        from_blog_id: item.id,
        to_blog_id: relatedBlog.id,
        link_text: "blogroll",
        link_url_raw: relatedBlog.url,
        neighbor_blog: relatedBlog,
      },
    ],
    recommended_blogs: [
      {
        ...recommendedBlog,
        via_blogs: [viaBlog],
      },
    ],
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

class TestResizeObserver {
  callback: ResizeObserverCallback;

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }

  observe() {
    this.callback(
      [
        {
          contentRect: { width: 960, height: 720 },
        } as ResizeObserverEntry,
      ],
      this,
    );
  }

  unobserve() {}

  disconnect() {}
}

beforeEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.stubGlobal("ResizeObserver", TestResizeObserver);
  forceGraphProps.length = 0;
  window.history.replaceState({}, "", "/");
  catalogItems = [...baseCatalogItems, makeCatalogItem(33, "PROCESSING", "Newest Processing Blog")];
  window.localStorage.clear();
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
      const urlQuery = (url.searchParams.get("url") || "").trim().toLowerCase();
      const sort = url.searchParams.get("sort") || "id_asc";
      const filteredItems = sortCatalogItems(
        (status ? catalogItems.filter((item) => item.crawl_status === status) : catalogItems).filter((item) => {
          if (!query && !urlQuery) {
            return true;
          }
          const title = String(item.title ?? "").toLowerCase();
          const blogUrl = String(item.url ?? "").toLowerCase();
          const normalizedUrl = String(item.normalized_url ?? "").toLowerCase();
          return (
            (!query || title.includes(query) || blogUrl.includes(query)) &&
            (!urlQuery || blogUrl.includes(urlQuery) || normalizedUrl.includes(urlQuery))
          );
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
    const blogDetailMatch = url.pathname.match(/^\/api\/blogs\/(\d+)$/);
    if (blogDetailMatch) {
      const detailItem = catalogItems.find((item) => Number(item.id) === Number(blogDetailMatch[1]));
      if (!detailItem) {
        return new Response(JSON.stringify({ detail: "not_found" }), { status: 404 });
      }
      return new Response(JSON.stringify(makeDetailPayload(detailItem)));
    }
    if (url.pathname === "/api/status") {
      return new Response(JSON.stringify(statusPayload));
    }
    if (url.pathname === "/api/stats") {
      return new Response(JSON.stringify({ total_blogs: statusPayload.total_blogs, total_edges: statusPayload.total_edges }));
    }
    if (url.pathname === "/api/filter-stats") {
      return new Response(
        JSON.stringify({
          by_filter_reason: {
            raw: 100,
            "rule:same_domain": 80,
            "rule:platform_blocked": 60,
            success: 45,
            blogs: 40,
          },
          rule_drops: {
            "rule:same_domain": 20,
            "rule:platform_blocked": 20,
          },
          success_sources: {
            rss: 18,
            model: 27,
            unknown: 0,
          },
          funnel: {
            raw: 100,
            after_rules: 60,
            model_rejected: 15,
            success: 45,
            blogs: 40,
          },
        }),
      );
    }
    if (url.pathname === "/api/graph/views/core") {
      return new Response(
        JSON.stringify({
          nodes: [
            {
              id: 1,
              url: "https://graph.example.com/",
              domain: "graph.example.com",
              title: "Graph Example",
              icon_url: null,
              incoming_count: 2,
              outgoing_count: 1,
            },
            {
              id: 2,
              url: "https://two.example.com/",
              domain: "two.example.com",
              title: "Two Example",
              icon_url: null,
              incoming_count: 1,
              outgoing_count: 1,
            },
            {
              id: 3,
              url: "https://three.example.com/",
              domain: "three.example.com",
              title: "Three Example",
              icon_url: null,
              incoming_count: 1,
              outgoing_count: 1,
            },
            {
              id: 4,
              url: "https://leaf.example.com/",
              domain: "leaf.example.com",
              title: "Leaf Example",
              icon_url: null,
              incoming_count: 0,
              outgoing_count: 1,
            },
          ],
          edges: [
            {
              id: "edge-1-2",
              from_blog_id: 1,
              to_blog_id: 2,
              link_text: null,
              link_url_raw: "https://two.example.com/",
            },
            {
              id: "edge-2-3",
              from_blog_id: 2,
              to_blog_id: 3,
              link_text: null,
              link_url_raw: "https://three.example.com/",
            },
            {
              id: "edge-3-1",
              from_blog_id: 3,
              to_blog_id: 1,
              link_text: null,
              link_url_raw: "https://graph.example.com/",
            },
            {
              id: "edge-1-4",
              from_blog_id: 1,
              to_blog_id: 4,
              link_text: null,
              link_url_raw: "https://leaf.example.com/",
            },
          ],
          meta: {
            strategy: "degree",
            limit: 200,
          },
        }),
      );
    }
    if (url.pathname === "/benchmarks/blog-community-graph.json") {
      return new Response(
        JSON.stringify({
          nodes: [
            {
              id: 1,
              url: "https://benchmark.heyblog.local/indie-web-01/",
              domain: "indie-web-01.benchmark.heyblog.local",
              title: "Indie Web Notes 01",
              icon_url: null,
              incoming_count: 1,
              outgoing_count: 1,
              degree: 2,
              component_id: "indie-web",
            },
            {
              id: 2,
              url: "https://benchmark.heyblog.local/indie-web-02/",
              domain: "indie-web-02.benchmark.heyblog.local",
              title: "Indie Web Notes 02",
              icon_url: null,
              incoming_count: 1,
              outgoing_count: 1,
              degree: 2,
              component_id: "indie-web",
            },
          ],
          edges: [
            {
              id: "benchmark-edge-001",
              from_blog_id: 1,
              to_blog_id: 2,
              link_text: "blogroll",
              link_url_raw: "https://benchmark.heyblog.local/indie-web-02/",
            },
          ],
          meta: {
            strategy: "synthetic-community-benchmark",
            limit: 2,
            total_nodes: 2,
            total_edges: 1,
          },
        }),
      );
    }
    throw new Error(`Unhandled fetch: ${url.toString()}`);
  });

  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.useRealTimers();
});

test("renders the home summary with URL search while keeping queue metrics and catalog cards hidden", async () => {
  render(<App />);

  await waitFor(() => {
    expect(screen.getByRole("heading", { name: "HeyBlog!" })).toBeInTheDocument();
  });
  expect(screen.getByText("基于友链爬取所有博客！")).toBeInTheDocument();
  expect(screen.getByText("总节点数")).toBeInTheDocument();
  expect(screen.getByText("总连接数")).toBeInTheDocument();
  expect(screen.getByText("34")).toBeInTheDocument();
  expect(screen.getByText("10")).toBeInTheDocument();
  expect(screen.queryByText("待处理队列")).not.toBeInTheDocument();
  expect(screen.queryByText("处理中 / 失败")).not.toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalledWith(expect.stringContaining("/api/status"), expect.anything());

  expect(fetch).not.toHaveBeenCalledWith(expect.stringContaining("/api/blogs/catalog"), expect.anything());
  expect(screen.queryByRole("button", { name: "ALL" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "PROCESSING" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "WAITING" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "FINISHED" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "FAILED" })).not.toBeInTheDocument();
  expect(screen.queryByText("Processing Blog")).not.toBeInTheDocument();
  expect(screen.queryByText("Waiting Blog")).not.toBeInTheDocument();
  expect(screen.queryByText("Finished Blog")).not.toBeInTheDocument();
  expect(screen.queryByText("Failed Blog")).not.toBeInTheDocument();
  expect(screen.getByPlaceholderText("输入你的博客链接，看看你的博客有没有被找到吧！")).toBeInTheDocument();

  await act(async () => {
    await vi.advanceTimersByTimeAsync(5000);
  });

  await waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/api/stats"), expect.anything());
  });
  expect(fetch).not.toHaveBeenCalledWith(expect.stringContaining("/api/blogs/catalog"), expect.anything());
  expect(fetch).not.toHaveBeenCalledWith(expect.stringContaining("/api/status"), expect.anything());
});

test("lets home users search normalized URLs and open the blog detail route", async () => {
  catalogItems = catalogItems.map((item) =>
    Number(item.id) === 3 ? { ...item, icon_url: "https://finished-blog.example.com/favicon.ico" } : item,
  );
  render(<App />);

  const input = await screen.findByPlaceholderText("输入你的博客链接，看看你的博客有没有被找到吧！");
  fireEvent.change(input, { target: { value: "finished-blog.example.com" } });
  fireEvent.click(screen.getByRole("button", { name: "搜索博客" }));

  await waitFor(() => {
    const searchCall = vi
      .mocked(fetch)
      .mock.calls.find(([input]) => String(input).includes("/api/blogs/catalog?"));
    expect(searchCall).toBeDefined();
    const requestUrl = new URL(String(searchCall![0]), "http://localhost");
    expect(requestUrl.searchParams.get("page")).toBe("1");
    expect(requestUrl.searchParams.get("page_size")).toBe("30");
    expect(requestUrl.searchParams.get("url")).toBe("finished-blog.example.com");
    expect(requestUrl.searchParams.get("sort")).toBe("id_desc");
  });
  expect(screen.getByText("1 个匹配")).toBeInTheDocument();
  expect(screen.getByText("Finished Blog")).toBeInTheDocument();
  expect(screen.getByText("https://finished-blog.example.com/")).toBeInTheDocument();
  expect(screen.getByAltText("finished-blog.example.com icon")).toHaveAttribute(
    "src",
    "https://finished-blog.example.com/favicon.ico",
  );

  fireEvent.click(screen.getByRole("button", { name: /Finished Blog/i }));

  await waitFor(() => {
    expect(window.location.pathname).toBe("/blogs/3");
  });
  expect(screen.queryByRole("heading", { name: "HeyBlog!" })).not.toBeInTheDocument();
  await waitFor(() => {
    expect(screen.getByRole("heading", { name: "Finished Blog" })).toBeInTheDocument();
  });
  expect(screen.getByAltText("finished-blog.example.com icon")).toHaveAttribute(
    "src",
    "https://finished-blog.example.com/favicon.ico",
  );
  expect(screen.getByRole("heading", { name: "直接相关博客" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "推荐博客" })).toBeInTheDocument();
  expect(screen.getByText("通过 Mutual Blog 关联")).toBeInTheDocument();
});

test("adds a random blog route that loads nine finished cards and refreshes them on demand", async () => {
  window.history.replaceState({}, "", "/random");

  render(<App />);

  await waitFor(() => {
    expect(screen.getByText("由于技术原因，目前仍然可能爬取到大量非博客节点")).toBeInTheDocument();
  });

  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/api/blogs/catalog?page=1&page_size=9&sort=random&status=FINISHED"),
    expect.anything(),
  );
  expect(screen.getByText("当前展示 9 个随机博客卡片")).toBeInTheDocument();
  expect(screen.getByText("Extra Blog 32")).toBeInTheDocument();
  expect(screen.getByAltText("extra-blog-32.example.com icon")).toHaveAttribute(
    "src",
    "https://t2.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://extra-blog-32.example.com&size=64",
  );

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

test("lets visualization users choose a graph size with a blog-count slider", async () => {
  window.history.replaceState({}, "", "/visualization");

  render(<App />);

  await waitFor(() => {
    expect(screen.getByRole("heading", { name: "博客关系图谱" })).toBeInTheDocument();
  });

  expect(screen.getByRole("dialog", { name: "选择图谱规模" })).toBeInTheDocument();
  const slider = await screen.findByRole("slider", { name: "节点数量" });
  expect(slider).toHaveAttribute("min", "0");
  expect(slider).toHaveAttribute("max", "34");
  expect(slider).toHaveValue("34");
  expect(screen.queryByText(/使用固定随机种子 42 选择起点/)).not.toBeInTheDocument();
  expect(screen.queryByText(/显示实际下载大小/)).not.toBeInTheDocument();
  expect(screen.queryByText("该功能仍不成熟！")).not.toBeInTheDocument();
  expect(screen.queryByText("数据统计")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "精简" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("button", { name: "全" })).toHaveAttribute("aria-pressed", "false");

  fireEvent.change(slider, { target: { value: "20" } });
  expect(slider).toHaveValue("20");
  fireEvent.click(screen.getByRole("button", { name: "确认" }));

  await waitFor(() => {
    expect(screen.getByRole("dialog", { name: "正在渲染图谱" })).toBeInTheDocument();
  });

  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/api/graph/views/core?strategy=seed&limit=20"),
    expect.anything(),
  );
  expect(forceGraphProps.at(-1)!.graphData.nodes.map((node: { id: string }) => node.id)).toEqual(["1", "2", "3"]);
  expect(forceGraphProps.at(-1)!.graphData.links).toHaveLength(3);
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "12");
  await waitFor(() => {
    expect(screen.getByText("预计需要 126 ticks")).toBeInTheDocument();
  });
  expect(screen.getByText("预估所需渲染时间：约 3 秒")).toBeInTheDocument();
  act(() => {
    forceGraphProps.at(-1)!.onEngineTick();
    forceGraphProps.at(-1)!.onEngineTick();
  });
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "12");
  act(() => {
    forceGraphProps.at(-1)!.onEngineStop();
  });
  await waitFor(() => {
    expect(screen.queryByRole("dialog", { name: "正在渲染图谱" })).not.toBeInTheDocument();
  });
  expect(screen.queryByText(/当前使用固定随机种子 42 展示 20 个节点/)).not.toBeInTheDocument();
  expect(screen.queryByText("全图最大节点数")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /刷新全图|返回全图/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /搜索博客/i })).not.toBeInTheDocument();
});

test("lets visualization users load the full graph without compact filtering", async () => {
  window.history.replaceState({}, "", "/visualization");

  render(<App />);

  const fullButton = await screen.findByRole("button", { name: "全" });
  fireEvent.click(fullButton);
  expect(fullButton).toHaveAttribute("aria-pressed", "true");

  fireEvent.click(screen.getByRole("button", { name: "确认" }));

  await waitFor(() => {
    expect(forceGraphProps.at(-1)!.graphData.nodes).toHaveLength(4);
  });
  expect(forceGraphProps.at(-1)!.graphData.links).toHaveLength(4);
});

test("ignores stale cached visualization graph data and reloads sampled sizes online", async () => {
  window.history.replaceState({}, "", "/visualization");
  window.localStorage.setItem(
    "heyblog:visualization:3d-v1:seed-42:limit-200",
    JSON.stringify({
      nodes: [
        {
          id: 88,
          url: "https://cached.example.com/",
          domain: "cached.example.com",
          title: "Cached Example",
          iconUrl: null,
        },
      ],
      edges: [],
    }),
  );

  render(<App />);

  await waitFor(() => {
    expect(screen.getByRole("dialog", { name: "选择图谱规模" })).toBeInTheDocument();
  });

  fireEvent.change(screen.getByRole("slider", { name: "节点数量" }), { target: { value: "20" } });
  fireEvent.click(screen.getByRole("button", { name: "确认" }));

  await waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/graph/views/core?strategy=seed&limit=20"),
      expect.anything(),
    );
  });
});

test("defaults visualization slider to two hundred when the blog count is larger", async () => {
  statusPayload = {
    ...statusPayload,
    total_blogs: 500,
  };
  window.history.replaceState({}, "", "/visualization");

  render(<App />);

  const slider = await screen.findByRole("slider", { name: "节点数量" });

  expect(slider).toHaveAttribute("max", "500");
  expect(slider).toHaveValue("200");
});

test("loads the static clustered benchmark graph through the visualization route", async () => {
  window.history.replaceState({}, "", "/visualization/benchmark");

  render(<App />);

  await waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/benchmarks/blog-community-graph.json"),
      expect.anything(),
    );
  });
  expect(screen.queryByRole("dialog", { name: "选择图谱规模" })).not.toBeInTheDocument();
  expect(forceGraphProps.at(-1)!.graphData.nodes).toHaveLength(2);
  expect(forceGraphProps.at(-1)!.graphData.links).toHaveLength(1);
});

test("adds a public filter stats route that renders success-source split", async () => {
  window.history.replaceState({}, "", "/filter-stats");

  render(<App />);

  await waitFor(() => {
    expect(screen.getByText("Filter Stats")).toBeInTheDocument();
  });

  expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/api/filter-stats"), expect.anything());
  expect(screen.getByText("原始候选")).toBeInTheDocument();
  expect(screen.getByText("RSS 判定为博客")).toBeInTheDocument();
  expect(screen.getByText("模型判定为博客")).toBeInTheDocument();
  expect(screen.getByText("模型判定非博客")).toBeInTheDocument();
  expect(screen.getByText("rule:same_domain")).toBeInTheDocument();
  expect(screen.getByText("rule:platform_blocked")).toBeInTheDocument();
  expect(screen.getByText("100")).toBeInTheDocument();
  expect(screen.getByText("60")).toBeInTheDocument();
  expect(screen.getByText("18")).toBeInTheDocument();
  expect(screen.getByText("27")).toBeInTheDocument();
});
