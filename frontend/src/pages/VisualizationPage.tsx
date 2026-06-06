import { Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { BlogDetailPanel } from "../components/BlogDetailPanel";
import { GraphVisualization } from "../components/GraphVisualization";
import { Navigation } from "../components/Navigation";
import { fetchBenchmarkGraphData } from "../lib/benchmarkGraph";
import { fetchBlogDetail, fetchGraphData, fetchStats, fetchSubgraph } from "../lib/api";
import type { BlogDetail, GraphData, GraphNode } from "../types/graph";

const DEFAULT_GRAPH_LIMIT = 200;
const ESTIMATED_RENDER_TICKS_PER_SECOND = 60;
type GraphDisplayMode = "compact" | "full";

/**
 * Format a force-layout tick estimate as an approximate render duration.
 *
 * @param ticks Estimated force-layout tick count.
 * @returns Human-readable duration label.
 */
function formatEstimatedRenderTime(ticks: number): string {
  const seconds = Math.max(1, Math.ceil(ticks / ESTIMATED_RENDER_TICKS_PER_SECOND));
  return `约 ${seconds} 秒`;
}

/**
 * Keep only graph nodes connected to at least two distinct other nodes.
 *
 * @param graph Raw graph returned by the backend.
 * @returns Compact graph with filtered nodes and only edges between kept nodes.
 */
export function compactGraphData(graph: GraphData): GraphData {
  const neighborIdsByNodeId = new Map<number, Set<number>>();
  for (const node of graph.nodes) {
    neighborIdsByNodeId.set(node.id, new Set());
  }

  for (const edge of graph.edges) {
    if (!neighborIdsByNodeId.has(edge.source) || !neighborIdsByNodeId.has(edge.target) || edge.source === edge.target) {
      continue;
    }
    neighborIdsByNodeId.get(edge.source)?.add(edge.target);
    neighborIdsByNodeId.get(edge.target)?.add(edge.source);
  }

  const keptNodeIds = new Set(
    Array.from(neighborIdsByNodeId.entries())
      .filter(([, neighborIds]) => neighborIds.size >= 2)
      .map(([nodeId]) => nodeId),
  );

  return {
    ...graph,
    nodes: graph.nodes.filter((node) => keptNodeIds.has(node.id)),
    edges: graph.edges.filter((edge) => keptNodeIds.has(edge.source) && keptNodeIds.has(edge.target)),
  };
}

/**
 * Render the dedicated graph exploration route.
 *
 * @returns Visualization page UI.
 */
export function VisualizationPage() {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const isBenchmarkMode = location.pathname.endsWith("/benchmark") || searchParams.get("benchmark") === "community";
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], edges: [] });
  const [blogDetail, setBlogDetail] = useState<BlogDetail | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isStatsLoading, setIsStatsLoading] = useState(true);
  const [isRendering, setIsRendering] = useState(false);
  const [renderProgress, setRenderProgress] = useState(0);
  const [estimatedRenderTicks, setEstimatedRenderTicks] = useState<number | null>(null);
  const [maxGraphLimit, setMaxGraphLimit] = useState(0);
  const [pendingLimit, setPendingLimit] = useState(DEFAULT_GRAPH_LIMIT);
  const [selectedLimit, setSelectedLimit] = useState<number | null>(null);
  const [graphDisplayMode, setGraphDisplayMode] = useState<GraphDisplayMode>("compact");
  const [highlightNodeId, setHighlightNodeId] = useState<number | undefined>();
  const visibleGraphData = useMemo(
    () => (graphDisplayMode === "compact" ? compactGraphData(graphData) : graphData),
    [graphData, graphDisplayMode],
  );
  const shouldShowProgressOverlay = isLoading || isRendering;
  const progressPercent = useMemo(() => {
    const loadingFloor = isLoading ? 0.08 : 0;
    return Math.round(Math.max(loadingFloor, renderProgress) * 100);
  }, [isLoading, renderProgress]);
  const estimatedRenderTime = useMemo(
    () => (estimatedRenderTicks ? formatEstimatedRenderTime(estimatedRenderTicks) : null),
    [estimatedRenderTicks],
  );

  useEffect(() => {
    if (isBenchmarkMode) {
      void loadBenchmarkGraph();
      return;
    }
    void loadGraphLimitBounds();
  }, [isBenchmarkMode]);

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
   * Load the current graph-size slider range from public stats.
   *
   * @returns Promise resolved after slider bounds update.
   */
  async function loadGraphLimitBounds() {
    try {
      setIsStatsLoading(true);
      const stats = await fetchStats();
      const totalBlogs = Math.max(0, stats.totalNodes);
      setMaxGraphLimit(totalBlogs);
      setPendingLimit(Math.min(DEFAULT_GRAPH_LIMIT, totalBlogs));
    } catch {
      toast.error("图谱规模加载失败，请刷新页面重试。");
      setMaxGraphLimit(DEFAULT_GRAPH_LIMIT);
      setPendingLimit(DEFAULT_GRAPH_LIMIT);
    } finally {
      setIsStatsLoading(false);
    }
  }

  /**
   * Load the deterministic clustered graph benchmark from static frontend assets.
   *
   * @returns Promise resolved after benchmark graph state updates.
   */
  async function loadBenchmarkGraph() {
    setGraphDisplayMode("full");
    setSelectedLimit(100);
    setPendingLimit(100);
    setMaxGraphLimit(100);
    setBlogDetail(null);
    setHighlightNodeId(undefined);
    setIsRendering(false);
    setRenderProgress(0);
    setEstimatedRenderTicks(null);

    try {
      setIsStatsLoading(false);
      setIsLoading(true);
      const benchmarkGraph = await fetchBenchmarkGraphData();
      setRenderProgress(0.12);
      setIsRendering(true);
      setGraphData(benchmarkGraph);
    } catch {
      setSelectedLimit(null);
      setIsRendering(false);
      setRenderProgress(0);
      setEstimatedRenderTicks(null);
      toast.error("Benchmark 图谱加载失败，请先运行生成脚本。");
    } finally {
      setIsLoading(false);
    }
  }

  /**
   * Load the selected graph size using deterministic backend sampling.
   *
   * @param limit Requested node count.
   * @returns Promise resolved after graph state updates.
   */
  async function loadFullGraph(limit: number) {
    setSelectedLimit(limit);
    setBlogDetail(null);
    setHighlightNodeId(undefined);
    setIsRendering(false);
    setRenderProgress(0);
    setEstimatedRenderTicks(null);

    try {
      setIsLoading(true);
      const graphResponse = await fetchGraphData(limit);
      setRenderProgress(0.12);
      setIsRendering(true);
      setGraphData(graphResponse);
    } catch {
      setSelectedLimit(null);
      setIsRendering(false);
      setRenderProgress(0);
      setEstimatedRenderTicks(null);
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
    if (isBenchmarkMode) {
      const node = visibleGraphData.nodes.find((item) => item.id === blogId);
      if (!node) {
        return;
      }
      setBlogDetail({
        ...node,
        incomingLinks: node.incomingCount ?? 0,
        outgoingLinks: node.outgoingCount ?? 0,
        relatedNodes: [],
        recommendedBlogs: [],
      });
      setHighlightNodeId(blogId);
      return;
    }

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
      </div>

      <div className="relative min-h-0 flex-1">
        <GraphVisualization
          data={visibleGraphData}
          onNodeClick={handleNodeClick}
          highlightNodeId={highlightNodeId}
          useNodeIcons={!isBenchmarkMode}
          onRenderProgress={(progress) => setRenderProgress((current) => Math.max(current, progress))}
          onRenderTickEstimate={setEstimatedRenderTicks}
          onRenderComplete={() => {
            setRenderProgress(1);
            setIsRendering(false);
          }}
        />
        {blogDetail ? <BlogDetailPanel detail={blogDetail} onClose={handleCloseDetail} /> : null}
      </div>

      {!selectedLimit || shouldShowProgressOverlay ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4 backdrop-blur-sm">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="visualization-limit-title"
            className="w-full max-w-md rounded-2xl bg-white p-6 shadow-[0_24px_80px_rgba(15,23,42,0.36)]"
          >
            {!selectedLimit ? (
              <>
                <h2 id="visualization-limit-title" className="text-2xl font-semibold tracking-normal text-slate-950">
                  选择图谱规模
                </h2>
                {isStatsLoading ? (
                  <div className="mt-5 flex items-center gap-3 text-sm text-slate-600">
                    <Loader2 className="h-4 w-4 animate-spin text-sky-500" />
                    正在读取博客数量...
                  </div>
                ) : (
                  <div className="mt-6">
                    <div className="flex items-end justify-between gap-4">
                      <div className="text-sm text-slate-500">节点数量</div>
                      <div className="text-3xl font-semibold tabular-nums text-slate-950">{pendingLimit}</div>
                    </div>
                    <div className="mt-5 grid grid-cols-2 overflow-hidden rounded-lg border border-slate-200 bg-slate-50 p-1">
                      <button
                        type="button"
                        onClick={() => setGraphDisplayMode("compact")}
                        className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                          graphDisplayMode === "compact" ? "bg-slate-950 text-white shadow-sm" : "text-slate-600 hover:bg-white"
                        }`}
                        aria-pressed={graphDisplayMode === "compact"}
                      >
                        精简
                      </button>
                      <button
                        type="button"
                        onClick={() => setGraphDisplayMode("full")}
                        className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                          graphDisplayMode === "full" ? "bg-slate-950 text-white shadow-sm" : "text-slate-600 hover:bg-white"
                        }`}
                        aria-pressed={graphDisplayMode === "full"}
                      >
                        全
                      </button>
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={maxGraphLimit}
                      step={1}
                      value={pendingLimit}
                      onChange={(event) => setPendingLimit(Number(event.currentTarget.value))}
                      className="mt-5 w-full accent-sky-500"
                      aria-label="节点数量"
                    />
                    <div className="mt-2 flex items-center justify-between text-sm tabular-nums text-slate-500">
                      <span>0</span>
                      <span>{maxGraphLimit}</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => void loadFullGraph(pendingLimit)}
                      disabled={isLoading || isStatsLoading}
                      className="mt-6 w-full rounded-xl bg-slate-950 px-4 py-3 text-sm font-medium text-white transition-colors hover:bg-sky-600 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      确认
                    </button>
                  </div>
                )}
              </>
            ) : (
              <div>
                <h2 id="visualization-limit-title" className="text-2xl font-semibold tracking-normal text-slate-950">
                  正在渲染图谱
                </h2>
                <div className="mt-5 flex items-center gap-3 text-sm text-slate-600">
                  <Loader2 className="h-4 w-4 animate-spin text-sky-500" />
                  {isLoading ? "正在加载图谱数据..." : "正在计算 3D 力导布局..."}
                </div>
                {!isLoading && estimatedRenderTicks ? (
                  <div className="mt-3 space-y-1 text-sm tabular-nums text-slate-500">
                    <div>预计需要 {estimatedRenderTicks} ticks</div>
                    {estimatedRenderTime ? <div>预估所需渲染时间：{estimatedRenderTime}</div> : null}
                  </div>
                ) : null}
                <div
                  className="mt-5 h-2 overflow-hidden rounded-full bg-slate-100"
                  role="progressbar"
                  aria-valuenow={progressPercent}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <div
                    className="h-full rounded-full bg-sky-500 transition-all duration-150 ease-out"
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>
                <div className="mt-2 text-right text-sm tabular-nums text-slate-500">{progressPercent}%</div>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
