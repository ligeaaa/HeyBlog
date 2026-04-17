import { beforeEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

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

const coreGraphResponse = {
  nodes: [
    {
      id: 1,
      url: "https://blog.example.com/",
      domain: "blog.example.com",
      title: "Blog Example",
      icon_url: null,
      x: 100,
      y: 120,
      degree: 2,
      incoming_count: 1,
      outgoing_count: 1,
      priority_score: 200,
      component_id: "component-1",
    },
  ],
  edges: [],
  meta: {
    strategy: "degree",
    limit: 180,
    has_stable_positions: true,
    snapshot_version: "v1",
    generated_at: "2026-04-16T15:00:00Z",
    source: "legacy:snapshot",
    total_nodes: 1,
    total_edges: 0,
    available_nodes: 1,
    available_edges: 0,
    selected_nodes: 1,
    selected_edges: 0,
    snapshot_namespace: "legacy",
  },
};

beforeEach(() => {
  cleanup();
  vi.restoreAllMocks();
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/graph/views/core")) {
      return new Response(JSON.stringify(coreGraphResponse));
    }
    if (url.includes("/api/stats")) {
      return new Response(JSON.stringify({ total_blogs: 6, total_edges: 10 }));
    }
    if (url.includes("/api/blogs/lookup")) {
      return new Response(
        JSON.stringify({
          query_url: "https://missing.example/",
          normalized_query_url: "https://missing.example/",
          items: [],
          total_matches: 0,
          match_reason: null,
        }),
      );
    }
    if (url.includes("/api/ingestion-requests")) {
      return new Response(JSON.stringify({ request_id: 9, request_token: "token", status: "QUEUED" }));
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });
  vi.stubGlobal(
    "fetch",
    fetchMock,
  );
});

test("renders the graph explorer and opens the real submit dialog on lookup miss", async () => {
  render(<App />);

  await waitFor(() => {
    expect(screen.getByRole("heading", { name: /博客关系网络可视化/i })).toBeInTheDocument();
  });

  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/api/graph/views/core?strategy=degree&limit=200"),
    expect.anything(),
  );
  expect(screen.getByDisplayValue("200")).toBeInTheDocument();
  expect(screen.getByText(/现在页面直接使用真实/i)).toBeInTheDocument();
  expect(screen.getByText("6")).toBeInTheDocument();
  expect(screen.getByText("10")).toBeInTheDocument();

  fireEvent.change(screen.getByPlaceholderText(/输入博客URL进行搜索/i), {
    target: { value: "https://missing.example/" },
  });
  fireEvent.click(screen.getByRole("button", { name: /搜索博客 URL/i }));

  await waitFor(() => {
    expect(screen.getByRole("heading", { name: /博客未找到/i })).toBeInTheDocument();
  });

  fireEvent.change(screen.getByPlaceholderText(/you@example.com/i), {
    target: { value: "owner@example.com" },
  });
  fireEvent.click(screen.getByRole("button", { name: /创建抓取请求/i }));

  await waitFor(() => {
    expect(screen.queryByRole("heading", { name: /博客未找到/i })).not.toBeInTheDocument();
  });
});
