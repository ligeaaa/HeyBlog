import { forwardRef, useImperativeHandle } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ApiError } from "../lib/api";
import { BlogDetailPage } from "./BlogDetailPage";
import { useBlogDetailView, useGraphNeighbors } from "../lib/hooks";

const mockRendererSpies = {
  captureViewport: vi.fn(() => ({ x: 0, y: 0, k: 1 })),
  restoreViewport: vi.fn(),
  fitView: vi.fn(),
  requestRelayout: vi.fn(),
  clearSelection: vi.fn(),
};

vi.mock("../components/graph/D3GraphCanvas", () => ({
  D3GraphCanvas: forwardRef(function MockD3GraphCanvas(
    { selectedNodeId }: { selectedNodeId: string | null },
    ref,
  ) {
    useImperativeHandle(ref, () => ({
      captureViewport: mockRendererSpies.captureViewport,
      restoreViewport: mockRendererSpies.restoreViewport,
      fitView: mockRendererSpies.fitView,
      requestRelayout: mockRendererSpies.requestRelayout,
      clearSelection: mockRendererSpies.clearSelection,
    }));
    return <div data-testid="blog-detail-graph">selected:{selectedNodeId ?? "none"}</div>;
  }),
}));

vi.mock("../components/graph/GraphInspector", () => ({
  GraphInspector: ({ details }: { details: { label: string } | null }) => (
    <div data-testid="graph-inspector">{details?.label ?? "empty"}</div>
  ),
}));

vi.mock("../lib/hooks", () => ({
  useBlogDetailView: vi.fn(),
  useGraphNeighbors: vi.fn(),
}));

const mockedUseBlogDetailView = vi.mocked(useBlogDetailView);
const mockedUseGraphNeighbors = vi.mocked(useGraphNeighbors);

function renderDetailPage(initialEntry = "/blogs/1") {
  const router = createMemoryRouter([{ path: "/blogs/:blogId", element: <BlogDetailPage /> }], {
    initialEntries: [initialEntry],
  });

  render(<RouterProvider router={router} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockRendererSpies.captureViewport.mockReset();
  mockRendererSpies.captureViewport.mockReturnValue({ x: 0, y: 0, k: 1 });
  mockRendererSpies.restoreViewport.mockReset();
  mockRendererSpies.fitView.mockReset();
  mockRendererSpies.requestRelayout.mockReset();
  mockRendererSpies.clearSelection.mockReset();
  mockedUseBlogDetailView.mockReturnValue({
    blog: {
      id: 1,
      url: "https://alpha.example",
      normalized_url: "https://alpha.example",
      domain: "alpha.example",
      title: "Alpha Blog",
      icon_url: "https://alpha.example/favicon.ico",
      status_code: 200,
      crawl_status: "FINISHED",
      friend_links_count: 4,
      last_crawled_at: null,
      created_at: "2026-03-29T00:00:00Z",
      updated_at: "2026-03-29T00:00:00Z",
      incoming_count: 1,
      outgoing_count: 1,
      connection_count: 2,
      activity_at: "2026-03-29T00:00:00Z",
      identity_complete: true,
      recommended_blogs: [
        {
          reason: "mutual_connection",
          mutual_connection_count: 1,
          via_blogs: [
            {
              id: 2,
              domain: "beta.example",
              title: "Beta",
              icon_url: "https://beta.example/favicon.ico",
            },
          ],
          blog: {
            id: 4,
            url: "https://delta.example",
            normalized_url: "https://delta.example",
            domain: "delta.example",
            title: "Delta",
            icon_url: "https://delta.example/favicon.ico",
            status_code: 200,
            crawl_status: "FINISHED",
            friend_links_count: 2,
            last_crawled_at: null,
            created_at: "2026-03-29T00:00:00Z",
            updated_at: "2026-03-29T00:00:00Z",
            incoming_count: 1,
            outgoing_count: 0,
            connection_count: 1,
            activity_at: "2026-03-29T00:00:00Z",
            identity_complete: true,
          },
        },
      ],
      outgoing_edges: [],
    },
    incomingEdges: [],
    outgoingEdges: [],
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useBlogDetailView>);

  mockedUseGraphNeighbors.mockReturnValue({
    data: {
      nodes: [
        {
          id: 1,
          url: "https://alpha.example",
          normalized_url: "https://alpha.example",
          domain: "alpha.example",
          title: "Alpha Blog",
          icon_url: "https://alpha.example/favicon.ico",
          status_code: 200,
          crawl_status: "FINISHED",
          friend_links_count: 4,
          last_crawled_at: null,
          created_at: "2026-03-29T00:00:00Z",
          updated_at: "2026-03-29T00:00:00Z",
          incoming_count: 1,
          outgoing_count: 1,
          connection_count: 2,
          activity_at: "2026-03-29T00:00:00Z",
          identity_complete: true,
          x: 100,
          y: 100,
          degree: 2,
          priority_score: 10,
          component_id: "component-1",
        },
      ],
      edges: [],
      meta: {
        strategy: "neighbors",
        limit: 40,
        sample_mode: "off",
        sample_value: null,
        sample_seed: 7,
        sampled: false,
        focus_node_id: 1,
        hops: 1,
        has_stable_positions: true,
        snapshot_version: null,
        generated_at: "2026-03-31T00:00:00Z",
        source: "neighbors",
        total_nodes: 1,
        total_edges: 0,
        available_nodes: 1,
        available_edges: 0,
        selected_nodes: 1,
        selected_edges: 0,
        graph_fingerprint: "blog-detail-graph",
      },
    },
    isLoading: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
    dataUpdatedAt: Date.parse("2026-03-31T00:00:00Z"),
  } as unknown as ReturnType<typeof useGraphNeighbors>);
});

afterEach(() => {
  cleanup();
});

test("renders the relationship graph before collapsed friend-of-friend recommendations", () => {
  renderDetailPage();

  expect(mockedUseBlogDetailView).toHaveBeenCalledWith(1);
  expect(mockedUseGraphNeighbors).toHaveBeenCalledWith(
    expect.objectContaining({
      blogId: 1,
      hops: 1,
      limit: 40,
    }),
  );
  expect(screen.getByText("关系图谱")).toBeInTheDocument();
  expect(screen.getByTestId("blog-detail-graph")).toHaveTextContent("selected:1");
  expect(mockRendererSpies.requestRelayout).toHaveBeenCalledWith("full");
  expect(screen.getByText("展开推荐")).toBeInTheDocument();
  expect(screen.queryByText(/通过 Beta 认识/)).not.toBeInTheDocument();
});

test("expands friend-of-friend recommendations on demand", () => {
  renderDetailPage();

  fireEvent.click(screen.getByRole("button", { name: "展开推荐" }));

  expect(screen.getByText(/通过 Beta 认识/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "收起推荐" })).toHaveAttribute("aria-expanded", "true");
});

test("allows changing relationship graph depth", () => {
  renderDetailPage();

  fireEvent.change(screen.getByLabelText("关系图谱深度"), { target: { value: "2" } });

  expect(mockedUseGraphNeighbors).toHaveBeenLastCalledWith(
    expect.objectContaining({
      blogId: 1,
      hops: 2,
      limit: 120,
    }),
  );
});

test("shows a graph-unavailable message for non-finished blogs", () => {
  mockedUseBlogDetailView.mockReturnValue({
    blog: {
      id: 1,
      url: "https://alpha.example",
      normalized_url: "https://alpha.example",
      domain: "alpha.example",
      title: "Alpha Blog",
      icon_url: "https://alpha.example/favicon.ico",
      status_code: 200,
      crawl_status: "WAITING",
      friend_links_count: 0,
      last_crawled_at: null,
      created_at: "2026-03-29T00:00:00Z",
      updated_at: "2026-03-29T00:00:00Z",
      incoming_count: 0,
      outgoing_count: 0,
      connection_count: 0,
      activity_at: null,
      identity_complete: false,
      recommended_blogs: [],
      outgoing_edges: [],
    },
    incomingEdges: [],
    outgoingEdges: [],
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useBlogDetailView>);

  renderDetailPage();

  expect(mockedUseGraphNeighbors).toHaveBeenCalledWith(
    expect.objectContaining({
      blogId: 1,
      enabled: false,
    }),
  );
  expect(screen.getByText("当前博客还没完成抓取，关系图谱会在状态变成 FINISHED 后可用。")).toBeInTheDocument();
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
