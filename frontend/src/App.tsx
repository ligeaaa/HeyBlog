import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Toaster, toast } from "sonner";
import { BlogDetailPanel } from "./components/BlogDetailPanel";
import { GraphVisualization } from "./components/GraphVisualization";
import { SearchBar } from "./components/SearchBar";
import { StatsPanel } from "./components/StatsPanel";
import { SubmitBlogDialog } from "./components/SubmitBlogDialog";
import { fetchGraphData, fetchStats, fetchSubgraph, searchUrl } from "./lib/api";
import type { BlogDetail, BlogNode, GraphData, StatsData } from "./types/graph";

/**
 * Example-aligned single-page graph explorer.
 *
 * During this phase the graph uses fake data so we can focus on matching the
 * `frontend_example` visual and interaction structure first.
 *
 * @returns Root app component for the rebuilt frontend.
 */
export default function App() {
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], links: [] });
  const [stats, setStats] = useState<StatsData>({ totalNodes: 0, totalEdges: 0 });
  const [blogDetail, setBlogDetail] = useState<BlogDetail | null>(null);
  const [showSubmitDialog, setShowSubmitDialog] = useState(false);
  const [searchedUrl, setSearchedUrl] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSearching, setIsSearching] = useState(false);
  const [highlightNodeId, setHighlightNodeId] = useState<string | undefined>();
  const [viewMode, setViewMode] = useState<"full" | "subgraph">("full");

  useEffect(() => {
    void loadInitialData();
  }, []);

  /**
   * Load the full fake graph and summary metrics on first render.
   */
  async function loadInitialData() {
    try {
      setIsLoading(true);
      const [graphResponse, statsResponse] = await Promise.all([fetchGraphData(), fetchStats()]);
      setGraphData(graphResponse);
      setStats(statsResponse);
    } catch {
      toast.error("加载数据失败，请刷新页面重试");
    } finally {
      setIsLoading(false);
    }
  }

  /**
   * Search for a blog URL and either focus its subgraph or open the submit dialog.
   *
   * @param url URL entered in the search box.
   */
  async function handleSearch(url: string) {
    try {
      setIsSearching(true);
      setSearchedUrl(url);

      const result = await searchUrl(url);

      if (result) {
        setBlogDetail(result);
        setShowSubmitDialog(false);

        const subgraph = await fetchSubgraph(url);
        setGraphData(subgraph);
        setViewMode("subgraph");
        setHighlightNodeId(result.id);
        toast.success("找到该博客！");
      } else {
        setBlogDetail(null);
        setShowSubmitDialog(true);
        toast.info("该 URL 目前不在 fake graph 数据集中");
      }
    } catch {
      toast.error("搜索失败，请重试");
    } finally {
      setIsSearching(false);
    }
  }

  /**
   * Open detail for a clicked graph node.
   *
   * @param node Node selected in the visualization.
   */
  async function handleNodeClick(node: BlogNode) {
    try {
      const result = await searchUrl(node.url);
      if (result) {
        setBlogDetail(result);
        setHighlightNodeId(node.id);
      }
    } catch {
      toast.error("获取节点详情失败");
    }
  }

  /**
   * Clear the active detail selection.
   */
  function handleCloseDetail() {
    setBlogDetail(null);
    setHighlightNodeId(undefined);
  }

  /**
   * Restore the full fake graph after focusing a subgraph.
   */
  async function handleResetView() {
    try {
      setIsLoading(true);
      const graphResponse = await fetchGraphData();
      setGraphData(graphResponse);
      setViewMode("full");
      setBlogDetail(null);
      setHighlightNodeId(undefined);
      toast.success("已恢复全图视图");
    } catch {
      toast.error("恢复视图失败");
    } finally {
      setIsLoading(false);
    }
  }

  if (isLoading) {
    return (
      <div className="size-full flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-50">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-12 w-12 animate-spin text-blue-500" />
          <div className="text-lg text-gray-600">加载博客关系网络...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex size-full flex-col bg-white">
      <Toaster position="top-right" richColors />

      <div className="flex-shrink-0 border-b-2 border-gray-200 bg-white p-6 shadow-sm">
        <div className="mx-auto max-w-6xl">
          <h1 className="mb-3 text-center text-3xl text-gray-900">博客关系网络可视化</h1>
          <p className="mb-6 text-center text-sm text-gray-500">
            当前阶段先按 `frontend_example` 的 UI 结构推进，图谱数据暂时使用 fake data。
          </p>
          <SearchBar onSearch={handleSearch} isLoading={isSearching} />

          <div className="mt-4 flex justify-center gap-3">
            <button
              onClick={() => void handleResetView()}
              disabled={viewMode === "full"}
              className="rounded-md border-2 border-gray-300 px-4 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-400"
            >
              {viewMode === "full" ? "全图视图" : "返回全图"}
            </button>
            {viewMode === "subgraph" ? (
              <div className="flex items-center rounded-md bg-blue-50 px-4 py-2 text-sm text-blue-700">
                当前显示局部关系图
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <div className="relative min-h-0 flex-1">
        <GraphVisualization
          data={graphData}
          onNodeClick={handleNodeClick}
          highlightNodeId={highlightNodeId}
        />

        {blogDetail ? <BlogDetailPanel detail={blogDetail} onClose={handleCloseDetail} /> : null}

        {showSubmitDialog ? (
          <SubmitBlogDialog
            url={searchedUrl}
            onClose={() => setShowSubmitDialog(false)}
            onSuccess={loadInitialData}
          />
        ) : null}
      </div>

      <div className="flex-shrink-0">
        <StatsPanel totalNodes={stats.totalNodes} totalEdges={stats.totalEdges} />
      </div>
    </div>
  );
}
