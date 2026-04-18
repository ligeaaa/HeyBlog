import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { BlogDetailPanel } from "../components/BlogDetailPanel";
import { GraphVisualization } from "../components/GraphVisualization";
import { LookupResultsDialog } from "../components/LookupResultsDialog";
import { Navigation } from "../components/Navigation";
import { SearchBar } from "../components/SearchBar";
import { StatsPanel } from "../components/StatsPanel";
import { SubmitBlogDialog } from "../components/SubmitBlogDialog";
import {
  fetchBlogDetail,
  fetchBlogLookup,
  fetchGraphData,
  fetchStats,
  fetchSubgraph,
} from "../lib/api";
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
  const [showSubmitDialog, setShowSubmitDialog] = useState(false);
  const [lookupCandidates, setLookupCandidates] = useState<GraphNode[]>([]);
  const [searchedUrl, setSearchedUrl] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSearching, setIsSearching] = useState(false);
  const [highlightNodeId, setHighlightNodeId] = useState<number | undefined>();
  const [viewMode, setViewMode] = useState<"full" | "subgraph">("full");
  const [fullGraphLimitInput, setFullGraphLimitInput] = useState(String(DEFAULT_FULL_GRAPH_LIMIT));

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
   * Load the full graph view using the requested limit input.
   *
   * @returns Promise resolved after the graph finishes loading.
   */
  async function loadFullGraph() {
    const parsedLimit = Number.parseInt(fullGraphLimitInput, 10);
    const limit = Number.isFinite(parsedLimit) && parsedLimit > 0 ? parsedLimit : DEFAULT_FULL_GRAPH_LIMIT;

    try {
      setIsLoading(true);
      const [graphResponse, statsResponse] = await Promise.all([fetchGraphData(limit), fetchStats()]);
      setGraphData(graphResponse);
      setStats(statsResponse);
      setViewMode("full");
      setLookupCandidates([]);
      setFullGraphLimitInput(String(limit));
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
        setViewMode("subgraph");
      }
    } catch {
      toast.error("博客详情加载失败。");
    }
  }

  /**
   * Search one URL from the visualization route.
   *
   * @param url User-entered URL.
   * @returns Promise resolved after the lookup flow completes.
   */
  async function handleSearch(url: string) {
    try {
      setIsSearching(true);
      setSearchedUrl(url);
      setShowSubmitDialog(false);
      setLookupCandidates([]);

      const result = await fetchBlogLookup(url);
      if (result.totalMatches === 0) {
        setBlogDetail(null);
        setShowSubmitDialog(true);
        toast.info("该 URL 当前未收录，可以提交抓取请求。");
        return;
      }
      if (result.totalMatches === 1) {
        await openBlog(result.items[0].id, { loadNeighborhood: true });
        toast.success("已定位到对应博客。");
        return;
      }

      setLookupCandidates(result.items);
      toast.info("找到多个候选博客，请先选择目标。");
    } catch {
      toast.error("搜索失败，请稍后重试。");
    } finally {
      setIsSearching(false);
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

  /**
   * Handle one selected lookup candidate from the disambiguation dialog.
   *
   * @param node Chosen candidate node.
   * @returns Promise resolved after the target blog opens.
   */
  async function handleSelectLookupCandidate(node: GraphNode) {
    setLookupCandidates([]);
    await openBlog(node.id, { loadNeighborhood: true });
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
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500">
            这里保留当前真实 G6 图谱能力。你可以搜索 URL、切换全图上限、查看局部子图，并从节点侧栏继续探索邻居与推荐博客。
          </p>

          <div className="mt-6">
            <SearchBar onSearch={handleSearch} isLoading={isSearching} />
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
              <span>全图最大节点数</span>
              <input
                type="number"
                min={1}
                step={10}
                value={fullGraphLimitInput}
                onChange={(event) => setFullGraphLimitInput(event.target.value)}
                className="w-24 rounded-lg border border-slate-300 bg-white px-2 py-1 text-sm text-slate-900 focus:border-sky-500 focus:outline-none"
              />
            </label>
            <button
              type="button"
              onClick={() => void loadFullGraph()}
              className="rounded-xl border border-slate-200 px-4 py-2 text-sm text-slate-700 transition-colors hover:bg-slate-100"
            >
              {viewMode === "full" ? "刷新全图" : "返回全图"}
            </button>
            {viewMode === "subgraph" ? (
              <div className="rounded-xl bg-sky-50 px-4 py-2 text-sm text-sky-700">当前显示局部关系图</div>
            ) : null}
          </div>
        </div>
      </div>

      <div className="relative min-h-0 flex-1">
        <GraphVisualization data={graphData} onNodeClick={handleNodeClick} highlightNodeId={highlightNodeId} />
        {blogDetail ? <BlogDetailPanel detail={blogDetail} onClose={handleCloseDetail} /> : null}
      </div>

      <StatsPanel totalNodes={stats.totalNodes} totalEdges={stats.totalEdges} />

      {showSubmitDialog ? (
        <SubmitBlogDialog url={searchedUrl} onClose={() => setShowSubmitDialog(false)} onSuccess={loadFullGraph} />
      ) : null}

      {lookupCandidates.length > 0 ? (
        <LookupResultsDialog
          items={lookupCandidates}
          onClose={() => setLookupCandidates([])}
          onSelect={(item) => void handleSelectLookupCandidate(item)}
        />
      ) : null}
    </div>
  );
}
