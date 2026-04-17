import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Toaster, toast } from "sonner";
import { BlogDetailPanel } from "./components/BlogDetailPanel";
import { GraphVisualization } from "./components/GraphVisualization";
import { LookupResultsDialog } from "./components/LookupResultsDialog";
import { SearchBar } from "./components/SearchBar";
import { StatsPanel } from "./components/StatsPanel";
import { SubmitBlogDialog } from "./components/SubmitBlogDialog";
import {
  fetchBlogDetail,
  fetchBlogLookup,
  fetchGraphData,
  fetchStats,
  fetchSubgraph,
} from "./lib/api";
import type { BlogDetail, GraphData, GraphNode, StatsData } from "./types/graph";

/**
 * Single-page graph explorer backed by the real public graph APIs.
 *
 * @returns Root app component for graph exploration.
 */
export default function App() {
  const defaultFullGraphLimit = 200;
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
  const [fullGraphLimitInput, setFullGraphLimitInput] = useState(String(defaultFullGraphLimit));

  useEffect(() => {
    void loadInitialData();
  }, []);

  async function loadInitialData(): Promise<boolean> {
    const parsedLimit = Number.parseInt(fullGraphLimitInput, 10);
    const fullGraphLimit = Number.isFinite(parsedLimit) && parsedLimit > 0 ? parsedLimit : defaultFullGraphLimit;
    try {
      setIsLoading(true);
      const [graphResponse, statsResponse] = await Promise.all([fetchGraphData(fullGraphLimit), fetchStats()]);
      setGraphData(graphResponse);
      setStats(statsResponse);
      setLookupCandidates([]);
      setFullGraphLimitInput(String(fullGraphLimit));
      return true;
    } catch {
      toast.error("加载数据失败，请刷新页面重试");
      return false;
    } finally {
      setIsLoading(false);
    }
  }

  async function openBlog(blogId: number, options: { loadNeighborhood: boolean }) {
    const detail = await fetchBlogDetail(blogId);
    setBlogDetail(detail);
    setHighlightNodeId(blogId);
    if (options.loadNeighborhood) {
      const subgraph = await fetchSubgraph(blogId, 1, 120);
      setGraphData(subgraph);
      setViewMode("subgraph");
    }
  }

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
        toast.success("找到该博客！");
        return;
      }

      setLookupCandidates(result.items);
      toast.info("找到多个候选博客，请先选择目标。");
    } catch {
      toast.error("搜索失败，请重试");
    } finally {
      setIsSearching(false);
    }
  }

  async function handleNodeClick(node: GraphNode) {
    try {
      await openBlog(node.id, { loadNeighborhood: false });
    } catch {
      toast.error("获取节点详情失败");
    }
  }

  function handleCloseDetail() {
    setBlogDetail(null);
    setHighlightNodeId(undefined);
  }

  async function handleResetView() {
    const restored = await loadInitialData();
    if (!restored) {
      toast.error("恢复视图失败");
      return;
    }
    try {
      setViewMode("full");
      setBlogDetail(null);
      setHighlightNodeId(undefined);
      toast.success("已恢复全图视图");
    } catch {
      toast.error("恢复视图失败");
    }
  }

  async function handleSelectLookupCandidate(node: GraphNode) {
    setLookupCandidates([]);
    await openBlog(node.id, { loadNeighborhood: true });
    toast.success("已切换到选中的博客。");
  }

  if (isLoading) {
    return (
      <div className="flex size-full items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-50">
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
            现在页面直接使用真实 `/api/graph*` 与 `/api/blogs*` 数据，并由 G6 渲染交互图谱。
          </p>
          <SearchBar onSearch={handleSearch} isLoading={isSearching} />

          <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
            <label className="flex items-center gap-2 rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700">
              <span>全图最大节点数</span>
              <input
                type="number"
                min={1}
                step={10}
                value={fullGraphLimitInput}
                onChange={(event) => setFullGraphLimitInput(event.target.value)}
                className="w-24 rounded border border-gray-300 bg-white px-2 py-1 text-sm text-gray-900 focus:border-blue-500 focus:outline-none"
              />
            </label>
            <button
              onClick={() => void handleResetView()}
              disabled={isLoading}
              className="rounded-md border-2 border-gray-300 px-4 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-400"
            >
              {viewMode === "full" ? "刷新全图" : "返回全图"}
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

        {lookupCandidates.length > 0 ? (
          <LookupResultsDialog
            items={lookupCandidates}
            onClose={() => setLookupCandidates([])}
            onSelect={(item) => void handleSelectLookupCandidate(item)}
          />
        ) : null}
      </div>

      <div className="flex-shrink-0">
        <StatsPanel totalNodes={stats.totalNodes} totalEdges={stats.totalEdges} />
      </div>
    </div>
  );
}
