import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { BlogDetailPanel } from "../components/BlogDetailPanel";
import { GraphVisualization } from "../components/GraphVisualization";
import { Navigation } from "../components/Navigation";
import { StatsPanel } from "../components/StatsPanel";
import { fetchBlogDetail, fetchGraphData, fetchStats, fetchSubgraph } from "../lib/api";
import type { BlogDetail, GraphData, GraphNode, StatsData } from "../types/graph";

const DEFAULT_FULL_GRAPH_LIMIT = 200;

/**
 * Render the dedicated graph exploration route.
 *
 * @returns Visualization page UI.
 */
export function VisualizationPage() {
  const [searchParams] = useSearchParams();
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], edges: [] });
  const [stats, setStats] = useState<StatsData>({ totalNodes: 0, totalEdges: 0 });
  const [blogDetail, setBlogDetail] = useState<BlogDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [highlightNodeId, setHighlightNodeId] = useState<number | undefined>();
  const [showMaturityNotice, setShowMaturityNotice] = useState(true);

  useEffect(() => {
    void loadFullGraph();
  }, []);

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
   * Load the full graph view using the fixed default limit.
   *
   * @returns Promise resolved after the graph finishes loading.
   */
  async function loadFullGraph() {
    try {
      setIsLoading(true);
      const [graphResponse, statsResponse] = await Promise.all([
        fetchGraphData(DEFAULT_FULL_GRAPH_LIMIT),
        fetchStats(),
      ]);
      setGraphData(graphResponse);
      setStats(statsResponse);
    } catch {
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

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top,_rgba(56,189,248,0.18),_transparent_32%),linear-gradient(180deg,_#eef6ff_0%,_#ffffff_48%,_#f6fbff_100%)]">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-12 w-12 animate-spin text-sky-500" />
          <div className="text-lg text-slate-600">加载博客关系图谱...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-[radial-gradient(circle_at_top,_rgba(56,189,248,0.18),_transparent_32%),linear-gradient(180deg,_#eef6ff_0%,_#ffffff_48%,_#f6fbff_100%)]">
      <Navigation />

      <div className="border-b border-slate-200 bg-white/80 px-6 pb-6 pt-24 shadow-sm backdrop-blur-sm sm:px-8">
        <div className="mx-auto max-w-6xl">
          <h1 className="text-4xl text-slate-950">博客关系图谱</h1>
          <p className="mt-4 text-sm leading-6 text-slate-500">当前仅展示200个节点，功能待完善qwq</p>
        </div>
      </div>

      <div className="relative min-h-0 flex-1">
        <GraphVisualization data={graphData} onNodeClick={handleNodeClick} highlightNodeId={highlightNodeId} />
        {blogDetail ? <BlogDetailPanel detail={blogDetail} onClose={handleCloseDetail} /> : null}
      </div>

      <StatsPanel totalNodes={stats.totalNodes} totalEdges={stats.totalEdges} />

      {showMaturityNotice ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 px-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="visualization-maturity-title"
            className="w-full max-w-md rounded-[28px] bg-white p-6 shadow-[0_24px_80px_rgba(15,23,42,0.28)]"
          >
            <h2 id="visualization-maturity-title" className="text-2xl text-slate-950">
              该功能仍不成熟！
            </h2>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              当前图谱能力仍在持续打磨中，展示结果和交互体验都可能继续调整。
            </p>
            <div className="mt-6 flex justify-end">
              <button
                type="button"
                onClick={() => setShowMaturityNotice(false)}
                className="rounded-xl bg-slate-900 px-4 py-2 text-sm text-white transition-colors hover:bg-slate-700"
              >
                我知道了
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
