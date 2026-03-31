import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { GraphPage } from "./GraphPage";
import { useGraph } from "../lib/hooks";

vi.mock("../lib/hooks", () => ({
  useGraph: vi.fn(),
}));

vi.mock("react-cytoscapejs", async () => {
  const React = await import("react");

  return {
    default: function MockCytoscapeComponent(props: {
      elements: Array<{ data: Record<string, string> }>;
      cy?: (instance: {
        scratch: (key: string, value?: unknown) => unknown;
        on: (...args: unknown[]) => void;
        elements: () => { length: number; unselect: () => void };
        layout: () => { run: () => void };
        fit: () => void;
        center: () => void;
        zoom: (() => number) & ((value: number) => void);
        pan: (() => { x: number; y: number }) & ((value: { x: number; y: number }) => void);
        nodes: () => Array<{ id: () => string; position: () => { x: number; y: number } }>;
        $: () => { first: () => { nonempty: () => boolean; id: () => string } };
        $id: (id: string) => { nonempty: () => boolean; select: () => void };
      }) => void;
    }) {
      const handlersRef = React.useRef(new Map<string, (event: unknown) => void>());
      const scratchRef = React.useRef(new Map<string, unknown>());
      const selectedRef = React.useRef<string | null>(null);

      React.useEffect(() => {
        const collection = props.elements.map((element) => ({
          isNode: () => element.data.source == null,
          id: () => String(element.data.id),
          position: () => ({ x: 100, y: 120 }),
        })) as Array<{
          isNode: () => boolean;
          id: () => string;
          position: () => { x: number; y: number };
        }> & { unselect: () => void };

        collection.unselect = () => {
          selectedRef.current = null;
        };

        const instance = {
          scratch: (key: string, value?: unknown) => {
            if (value !== undefined) {
              scratchRef.current.set(key, value);
            }
            return scratchRef.current.get(key);
          },
          on: (...args: unknown[]) => {
            const eventName = String(args[0]);
            const handler = args[args.length - 1] as (event: unknown) => void;
            handlersRef.current.set(eventName, handler);
          },
          elements: () => collection,
          layout: () => ({ run: () => undefined }),
          fit: () => undefined,
          center: () => undefined,
          zoom: ((value?: number) => (value == null ? 1 : undefined)) as (() => number) & ((value: number) => void),
          pan: ((value?: { x: number; y: number }) => (value == null ? { x: 0, y: 0 } : undefined)) as (() => {
            x: number;
            y: number;
          }) &
            ((value: { x: number; y: number }) => void),
          nodes: () => collection.filter((element) => element.isNode()),
          $: () => ({
            first: () => ({
              nonempty: () => selectedRef.current != null,
              id: () => selectedRef.current ?? "",
            }),
          }),
          $id: (id: string) => ({
            nonempty: () => props.elements.some((element) => String(element.data.id) === id),
            select: () => {
              selectedRef.current = id;
            },
          }),
        };

        props.cy?.(instance);
      }, [props]);

      const nodeElements = props.elements.filter((element) => element.data.source == null);

      return (
        <div data-testid="mock-cytoscape">
          {nodeElements.map((element) => (
            <button
              key={String(element.data.id)}
              type="button"
              onClick={() => {
                selectedRef.current = String(element.data.id);
                handlersRef.current.get("select")?.({
                  target: {
                    id: () => String(element.data.id),
                  },
                });
              }}
            >
              {String(element.data.label)}
            </button>
          ))}
        </div>
      );
    },
  };
});

const mockedUseGraph = vi.mocked(useGraph);

beforeEach(() => {
  vi.clearAllMocks();
  mockedUseGraph.mockReturnValue({
    data: {
      nodes: [
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
      edges: [],
    },
    isLoading: false,
    isFetching: false,
    error: null,
    dataUpdatedAt: 1711737600000,
    refetch: vi.fn().mockResolvedValue(undefined),
  } as unknown as ReturnType<typeof useGraph>);
});

afterEach(() => {
  cleanup();
});

test("manual refresh button triggers refetch", async () => {
  const query = {
    data: {
      nodes: [
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
      edges: [],
    },
    isLoading: false,
    isFetching: false,
    error: null,
    dataUpdatedAt: 1711737600000,
    refetch: vi.fn().mockResolvedValue(undefined),
  };
  mockedUseGraph.mockReturnValue(query as unknown as ReturnType<typeof useGraph>);

  render(<GraphPage />);

  await userEvent.click(screen.getByRole("button", { name: "手动刷新" }));

  expect(query.refetch).toHaveBeenCalled();
});

test("selecting a node updates the inspector", async () => {
  render(<GraphPage />);

  await userEvent.click(screen.getByRole("button", { name: "alpha.example" }));

  expect(screen.getByText("Selected Node")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "alpha.example" })).toBeInTheDocument();
  expect(screen.getByText("https://alpha.example")).toBeInTheDocument();
});
