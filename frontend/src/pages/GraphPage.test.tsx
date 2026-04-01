import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { forwardRef, useImperativeHandle } from "react";
import { GraphPage } from "./GraphPage";
import { useGraphView } from "../lib/hooks";
import { api } from "../lib/api";

vi.mock("../lib/hooks", () => ({
  useGraphView: vi.fn(),
}));

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual("../lib/api");
  return {
    ...actual,
    api: {
      ...(actual as { api: object }).api,
      graphNeighbors: vi.fn().mockResolvedValue({
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
            friend_links_count: 3,
            source_blog_id: null,
            last_crawled_at: null,
            created_at: "2026-03-29T00:00:00Z",
            updated_at: "2026-03-29T00:00:00Z",
            x: 100,
            y: 120,
            degree: 2,
            incoming_count: 1,
            outgoing_count: 1,
            priority_score: 220,
            component_id: "component-1",
          },
          {
            id: 2,
            url: "https://beta.example",
            normalized_url: "https://beta.example",
            domain: "beta.example",
            title: "Beta Blog",
            icon_url: "https://beta.example/favicon.ico",
            status_code: 200,
            crawl_status: "FINISHED",
            friend_links_count: 1,
            source_blog_id: 1,
            last_crawled_at: null,
            created_at: "2026-03-31T00:00:00Z",
            updated_at: "2026-03-31T00:00:00Z",
            x: 160,
            y: 140,
            degree: 1,
            incoming_count: 1,
            outgoing_count: 0,
            priority_score: 110,
            component_id: "component-1",
          },
        ],
        edges: [
          {
            id: 11,
            from_blog_id: 1,
            to_blog_id: 2,
            link_url_raw: "https://beta.example",
            link_text: "beta",
            discovered_at: "2026-03-31T00:00:00Z",
          },
        ],
        meta: {
          strategy: "neighborhood",
          limit: 120,
          sample_mode: "off",
          sample_value: null,
          sample_seed: 0,
          sampled: false,
          focus_node_id: 1,
          hops: 1,
          has_stable_positions: true,
          snapshot_version: "v1",
          generated_at: "2026-03-31T00:00:00Z",
          source: "snapshot",
          total_nodes: 2,
          total_edges: 1,
          available_nodes: 2,
          available_edges: 1,
          selected_nodes: 2,
          selected_edges: 1,
        },
      }),
    },
  };
});

const mockRendererSpies = {
  captureViewport: vi.fn(() => ({ x: 0, y: 0, k: 1 })),
  restoreViewport: vi.fn(),
  fitView: vi.fn(),
  requestRelayout: vi.fn(),
  clearSelection: vi.fn(),
};

vi.mock("../components/graph/D3GraphCanvas", () => {
  return {
    D3GraphCanvas: forwardRef(function MockD3GraphCanvas(
      props: {
        scene: { nodes: Array<{ id: string; label: string }> };
        onSelect: (nodeId: string | null) => void;
      },
      ref,
    ) {
      useImperativeHandle(ref, () => ({
        captureViewport: mockRendererSpies.captureViewport,
        restoreViewport: mockRendererSpies.restoreViewport,
        fitView: mockRendererSpies.fitView,
        requestRelayout: mockRendererSpies.requestRelayout,
        clearSelection: mockRendererSpies.clearSelection,
      }));

      return (
        <div>
          <button type="button" onClick={() => props.onSelect(null)}>
            clear selection
          </button>
          {props.scene.nodes.map((node) => (
            <button key={node.id} type="button" onClick={() => props.onSelect(node.id)}>
              {node.label}
            </button>
          ))}
        </div>
      );
    }),
  };
});

const mockedUseGraphView = vi.mocked(useGraphView);
const mockedApi = vi.mocked(api);

function buildQueryResult() {
  return {
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
          friend_links_count: 3,
          source_blog_id: null,
          last_crawled_at: null,
          created_at: "2026-03-29T00:00:00Z",
          updated_at: "2026-03-29T00:00:00Z",
          x: 100,
          y: 120,
          degree: 2,
          incoming_count: 1,
          outgoing_count: 1,
          priority_score: 220,
          component_id: "component-1",
        },
      ],
      edges: [],
      meta: {
        strategy: "degree",
        limit: 180,
        sample_mode: "off" as const,
        sample_value: null,
        sample_seed: 7,
        sampled: false,
        focus_node_id: null,
        hops: null,
        has_stable_positions: true,
        snapshot_version: "v1",
        generated_at: "2026-03-31T00:00:00Z",
        source: "snapshot",
        total_nodes: 1,
        total_edges: 0,
        available_nodes: 1,
        available_edges: 0,
        selected_nodes: 1,
        selected_edges: 0,
      },
    },
    isLoading: false,
    isFetching: false,
    error: null,
    dataUpdatedAt: 1711737600000,
    refetch: vi.fn().mockResolvedValue(undefined),
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockRendererSpies.captureViewport.mockReset();
  mockRendererSpies.captureViewport.mockReturnValue({ x: 0, y: 0, k: 1 });
  mockRendererSpies.restoreViewport.mockReset();
  mockRendererSpies.fitView.mockReset();
  mockRendererSpies.requestRelayout.mockReset();
  mockRendererSpies.clearSelection.mockReset();
  mockedUseGraphView.mockReturnValue(buildQueryResult() as unknown as ReturnType<typeof useGraphView>);
});

afterEach(() => {
  cleanup();
});

test("manual refresh button triggers refetch", async () => {
  const query = buildQueryResult();
  mockedUseGraphView.mockReturnValue(query as unknown as ReturnType<typeof useGraphView>);

  render(<GraphPage />);

  await userEvent.click(screen.getByRole("button", { name: "手动刷新" }));

  expect(query.refetch).toHaveBeenCalled();
});

test("selecting a node updates the inspector", async () => {
  render(<GraphPage />);

  await userEvent.click(screen.getByRole("button", { name: "Alpha Blog" }));

  expect(screen.getByText("Selected Node")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Alpha Blog" })).toBeInTheDocument();
  expect(screen.getByRole("img", { name: "Alpha Blog icon" })).toBeInTheDocument();
  expect(screen.getByText("alpha.example")).toBeInTheDocument();
  expect(screen.getByText("https://alpha.example")).toBeInTheDocument();
});

test("sampling controls become visible when random mode is enabled", async () => {
  render(<GraphPage />);

  await userEvent.selectOptions(screen.getByLabelText("采样模式"), "count");

  expect(screen.getByLabelText("采样数量")).toBeInTheDocument();
  expect(screen.getByLabelText("固定 Seed")).toBeInTheDocument();
});

test("expanding a selected node requests neighborhood data", async () => {
  render(<GraphPage />);

  await userEvent.click(screen.getByRole("button", { name: "Alpha Blog" }));
  await userEvent.click(screen.getByRole("button", { name: "展开 1 跳" }));

  expect(mockedApi.graphNeighbors).toHaveBeenCalledWith("1", { hops: 1, limit: 180 });
});

test("reset restores the core graph after neighborhood expansion", async () => {
  render(<GraphPage />);

  await userEvent.click(screen.getByRole("button", { name: "Alpha Blog" }));
  await userEvent.click(screen.getByRole("button", { name: "展开 1 跳" }));

  expect(await screen.findByRole("button", { name: "Beta Blog" })).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "重置为核心视图" }));

  expect(screen.queryByRole("button", { name: "Beta Blog" })).not.toBeInTheDocument();
});

test("fit and relayout controls call the renderer contract", async () => {
  render(<GraphPage />);

  await userEvent.click(screen.getByRole("button", { name: "适配视图" }));
  await userEvent.click(screen.getByRole("button", { name: "重新布局" }));

  expect(mockRendererSpies.fitView).toHaveBeenCalled();
  expect(mockRendererSpies.requestRelayout).toHaveBeenCalledWith("full");
});

test("clicking the background clears the current selection", async () => {
  render(<GraphPage />);

  await userEvent.click(screen.getByRole("button", { name: "Alpha Blog" }));
  expect(screen.getByRole("heading", { name: "Alpha Blog" })).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "clear selection" }));

  expect(screen.queryByRole("heading", { name: "Alpha Blog" })).not.toBeInTheDocument();
});
