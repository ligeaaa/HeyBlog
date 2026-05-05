import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { BlogDetailPanel } from "../components/BlogDetailPanel";
import { GraphVisualization } from "../components/GraphVisualization";
import { Navigation } from "../components/Navigation";
import { fetchBlogDetail, fetchGraphData, fetchSubgraph } from "../lib/api";
import type { BlogDetail, GraphData, GraphNode } from "../types/graph";

const GRAPH_LIMIT_OPTIONS = [200, 500, 1000, 10000] as const;
const GRAPH_SAMPLE_SEED = 42;
const GRAPH_CACHE_VERSION = "3d-v1";

type GraphLimit = (typeof GRAPH_LIMIT_OPTIONS)[number];

function graphCacheKey(limit: GraphLimit): string {
  return `heyblog:visualization:${GRAPH_CACHE_VERSION}:seed-${GRAPH_SAMPLE_SEED}:limit-${limit}`;
}

function readCachedGraph(limit: GraphLimit): GraphData | null {
  try {
    const raw = window.localStorage.getItem(graphCacheKey(limit));
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as GraphData;
    if (Array.isArray(parsed.nodes) && Array.isArray(parsed.edges)) {
      return parsed;
    }
  } catch {
    window.localStorage.removeItem(graphCacheKey(limit));
  }
  return null;
}

function graphPayloadSizeMb(data: GraphData): string {
  const bytes = new TextEncoder().encode(JSON.stringify(data)).length;
  return (bytes / (1024 * 1024)).toFixed(2);
}

function writeCachedGraph(limit: GraphLimit, data: GraphData): void {
  try {
    window.localStorage.setItem(graphCacheKey(limit), JSON.stringify(data));
  } catch {
    // Browsers can reject large localStorage writes; graph rendering should still continue.
  }
}

/**
 * Render the dedicated graph exploration route.
 *
 * @returns Visualization page UI.
 */
export function VisualizationPage() {
  const [searchParams] = useSearchParams();
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], edges: [] });
  const [blogDetail, setBlogDetail] = useState<BlogDetail | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedLimit, setSelectedLimit] = useState<GraphLimit | null>(null);
  const [graphSizeMb, setGraphSizeMb] = useState<string | null>(null);
  const [usedCachedGraph, setUsedCachedGraph] = useState(false);
  const [highlightNodeId, setHighlightNodeId] = useState<number | undefined>();

  useEffect(() => {
    const highlight = searchParams.get("highlight");
    if (!highlight) {
      return;
    }
    const blogId = Number(highlight);
    if (!Number.isFinite(blogId)) {
      return;
    }
    void openBlog(blogId, { loadNeighborhood: true });
  }, [searchParams]);

  /**
   * Load the selected graph size using deterministic backend sampling.
   *
   * @param limit Requested node count.
   * @returns Promise resolved after graph state updates.
   */
  async function loadFullGraph(limit: GraphLimit) {
    setSelectedLimit(limit);
    setBlogDetail(null);
    setHighlightNodeId(undefined);

    const cachedGraph = readCachedGraph(limit);
    if (cachedGraph) {
      setGraphData(cachedGraph);
      setGraphSizeMb(graphPayloadSizeMb(cachedGraph));
      setUsedCachedGraph(true);
      return;
    }

    try {
      setUsedCachedGraph(false);
      setIsLoading(true);
      const graphResponse = await fetchGraphData(limit, { sampleMode: "count", sampleSeed: GRAPH_SAMPLE_SEED });
      setGraphData(graphResponse);
      setGraphSizeMb(graphPayloadSizeMb(graphResponse));
      writeCachedGraph(limit, graphResponse);
    } catch {
      setSelectedLimit(null);
      toast.error("图谱加载失败，请刷新页面重试。");
    } finally {
      setIsLoading(false);
    }
  }

  /**
   * Open one blog detail and optionally switch into its neighborhood graph.
   *
   * @param blogId Target blog id.
   * @param options Additional loading mode flags.
   * @returns Promise resolved after all requested data is loaded.
   */
  async function openBlog(blogId: number, options: { loadNeighborhood: boolean }) {
    try {
      const detail = await fetchBlogDetail(blogId);
      setBlogDetail(detail);
      setHighlightNodeId(blogId);
      if (options.loadNeighborhood) {
        const subgraph = await fetchSubgraph(blogId, 1, 120);
        setGraphData(subgraph);
      }
    } catch {
      toast.error("博客详情加载失败。");
    }
  }

  /**
   * Open one node from a graph click.
   *
   * @param node Clicked graph node.
   * @returns Promise resolved after the detail panel updates.
   */
  async function handleNodeClick(node: GraphNode) {
    await openBlog(node.id, { loadNeighborhood: false });
  }

  /**
   * Clear the active detail focus.
   */
  function handleCloseDetail() {
    setBlogDetail(null);
    setHighlightNodeId(undefined);
  }

  return (
    <div className="flex h-screen min-h-screen flex-col overflow-hidden bg-slate-950">
      <Navigation />

      <div className="absolute left-6 top-24 z-20 max-w-sm text-white sm:left-8">
        <h1 className="text-3xl font-semibold tracking-normal">博客关系图谱</h1>
        {selectedLimit ? (
          <p className="mt-2 text-sm leading-6 text-slate-300">
            当前使用固定随机种子 {GRAPH_SAMPLE_SEED} 展示 {selectedLimit} 个节点
            {graphSizeMb ? `，本次图谱数据约 ${graphSizeMb} MB` : ""}
            {usedCachedGraph ? "，已从本地缓存读取" : ""}
          </p>
        ) : null}
      </div>

      <div className="relative min-h-0 flex-1">
        <GraphVisualization data={graphData} onNodeClick={handleNodeClick} highlightNodeId={highlightNodeId} />
        {blogDetail ? <BlogDetailPanel detail={blogDetail} onClose={handleCloseDetail} /> : null}
      </div>

      {!selectedLimit || isLoading ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4 backdrop-blur-sm">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="visualization-limit-title"
            className="w-full max-w-md rounded-2xl bg-white p-6 shadow-[0_24px_80px_rgba(15,23,42,0.36)]"
          >
            <h2 id="visualization-limit-title" className="text-2xl font-semibold tracking-normal text-slate-950">
              选择图谱规模
            </h2>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              使用固定随机种子 {GRAPH_SAMPLE_SEED} 选择起点，并按 BFS 扩展关联节点。本地缓存命中时会直接读取已下载的数据。
            </p>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              选择后会先获取图谱 JSON，并显示实际下载大小（MB）。
            </p>
            <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {GRAPH_LIMIT_OPTIONS.map((limit) => (
                <button
                  key={limit}
                  type="button"
                  onClick={() => void loadFullGraph(limit)}
                  disabled={isLoading}
                  className="rounded-xl border border-slate-200 px-4 py-3 text-sm font-medium text-slate-900 transition-colors hover:border-sky-300 hover:bg-sky-50 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {limit}
                </button>
              ))}
            </div>
            {isLoading ? (
              <div className="mt-5 flex items-center gap-3 text-sm text-slate-600">
                <Loader2 className="h-4 w-4 animate-spin text-sky-500" />
                正在加载图谱数据...
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
