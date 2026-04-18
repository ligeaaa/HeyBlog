import { Loader2, Network, GitBranch, Radar, TimerReset } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { BlogCard } from "../components/BlogCard";
import { Navigation } from "../components/Navigation";
import { SearchBar } from "../components/SearchBar";
import { fetchBlogsCatalog, fetchStats, fetchStatus } from "../lib/api";
import type { BlogCatalogPage, StatsData, StatusData } from "../types/graph";

const DEFAULT_PAGE_SIZE = 30;
const HOME_REFRESH_INTERVAL_MS = 5000;
const HOME_STATUS_ORDER = ["PROCESSING", "WAITING", "FINISHED", "FAILED"] as const;
const HOME_STATUS_FILTERS = ["ALL", ...HOME_STATUS_ORDER] as const;

type HomeStatusFilter = (typeof HOME_STATUS_FILTERS)[number];

/**
 * Load one synthetic "ALL" page by concatenating status buckets in priority order.
 *
 * Each bucket is read directly from the catalog API and keeps ascending blog-id
 * ordering inside the bucket.
 *
 * @param page Current homepage page number.
 * @param pageSize Maximum number of cards per page.
 * @param searchQuery Optional fuzzy-search keyword applied to the catalog query.
 * @returns One combined catalog page.
 */
async function fetchAllStatusCatalogPage(
  page: number,
  pageSize: number,
  searchQuery: string,
): Promise<BlogCatalogPage> {
  const takeCount = page * pageSize;
  const responses = await Promise.all(
    HOME_STATUS_ORDER.map((status) =>
      fetchBlogsCatalog({
        page: 1,
        pageSize: takeCount,
        q: searchQuery || undefined,
        sort: "id_asc",
        status,
      }),
    ),
  );

  const mergedItems = responses.flatMap((response) => response.items);
  const offset = (page - 1) * pageSize;
  const totalItems = responses.reduce((sum, response) => sum + response.totalItems, 0);
  const totalPages = totalItems > 0 ? Math.ceil(totalItems / pageSize) : 0;

  return {
    items: mergedItems.slice(offset, offset + pageSize),
    page,
    pageSize,
    totalItems,
    totalPages,
    hasNext: page < totalPages,
    hasPrev: page > 1,
    sort: "home_status_priority_asc",
  };
}

/**
 * Render the public home page with stats, search, and card-based blog discovery.
 *
 * @returns Home route UI.
 */
export function HomePage() {
  const [catalog, setCatalog] = useState<BlogCatalogPage | null>(null);
  const [stats, setStats] = useState<StatsData>({ totalNodes: 0, totalEdges: 0 });
  const [status, setStatus] = useState<StatusData | null>(null);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [statusFilter, setStatusFilter] = useState<HomeStatusFilter>("ALL");
  const [currentPage, setCurrentPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState("");
  const refreshInFlightRef = useRef(false);
  const hasLoadedOnceRef = useRef(false);

  useEffect(() => {
    const isFirstLoad = !hasLoadedOnceRef.current;
    if (isFirstLoad) {
      hasLoadedOnceRef.current = true;
    }
    void loadHomePage({
      page: currentPage,
      searchQuery,
      statusFilter,
      showInitialLoading: isFirstLoad,
      showRefreshState: !isFirstLoad,
    });
  }, [currentPage, searchQuery, statusFilter]);

  useEffect(() => {
    let isDisposed = false;

    async function refreshFromTimer() {
      if (document.visibilityState !== "visible" || isDisposed) {
        return;
      }
      await loadHomePage({
        page: currentPage,
        searchQuery,
        statusFilter,
        showInitialLoading: false,
        showRefreshState: true,
        showErrorToast: false,
      });
    }

    const intervalId = window.setInterval(() => {
      void refreshFromTimer();
    }, HOME_REFRESH_INTERVAL_MS);

    function handleVisibilityChange() {
      if (document.visibilityState === "visible") {
        void loadHomePage({
          page: currentPage,
          searchQuery,
          statusFilter,
          showInitialLoading: false,
          showRefreshState: true,
          showErrorToast: false,
        });
      }
    }

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      isDisposed = true;
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [currentPage, searchQuery, statusFilter]);

  /**
   * Load the home page summary and one catalog page.
   *
   * @param options Loading behavior flags.
   * @returns Promise resolved when the homepage state finishes updating.
   */
  async function loadHomePage(options?: {
    page?: number;
    searchQuery?: string;
    statusFilter?: HomeStatusFilter;
    showInitialLoading?: boolean;
    showRefreshState?: boolean;
    showErrorToast?: boolean;
  }) {
    if (refreshInFlightRef.current) {
      return;
    }

    const showInitialLoading = options?.showInitialLoading ?? false;
    const showRefreshState = options?.showRefreshState ?? false;
    const showErrorToast = options?.showErrorToast ?? true;
    const page = options?.page ?? currentPage;
    const currentSearchQuery = options?.searchQuery ?? searchQuery;
    const selectedStatusFilter = options?.statusFilter ?? statusFilter;

    refreshInFlightRef.current = true;
    try {
      if (showInitialLoading) {
        setIsInitialLoading(true);
      }
      if (showRefreshState) {
        setIsRefreshing(true);
      }
      const [catalogResponse, statsResponse, statusResponse] = await Promise.all([
        selectedStatusFilter === "ALL"
          ? fetchAllStatusCatalogPage(page, DEFAULT_PAGE_SIZE, currentSearchQuery)
          : fetchBlogsCatalog({
              page,
              pageSize: DEFAULT_PAGE_SIZE,
              q: currentSearchQuery || undefined,
              sort: selectedStatusFilter === "WAITING" ? "id_asc" : "id_desc",
              status: selectedStatusFilter,
            }),
        fetchStats(),
        fetchStatus(),
      ]);
      setCatalog(catalogResponse);
      setStats(statsResponse);
      setStatus(statusResponse);
    } catch {
      if (showErrorToast) {
        toast.error("首页数据加载失败，请刷新页面重试。");
      }
    } finally {
      refreshInFlightRef.current = false;
      setIsInitialLoading(false);
      setIsRefreshing(false);
      setIsSearching(false);
    }
  }

  /**
   * Update the selected homepage status filter and reset pagination to the oldest page.
   *
   * @param filter Next status filter selected by the user.
   */
  function handleStatusFilterChange(filter: HomeStatusFilter) {
    setStatusFilter(filter);
    setCurrentPage(1);
  }

  /**
   * Apply one fuzzy-search keyword to the homepage catalog.
   *
   * @param query Search keyword entered by the user.
   */
  function handleSearch(query: string) {
    setIsSearching(true);
    setSearchQuery(query);
    setCurrentPage(1);
  }

  if (isInitialLoading || !catalog) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-12 w-12 animate-spin text-sky-500" />
          <div className="text-lg text-slate-600">正在加载首页内容...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen overflow-x-hidden bg-white">
      <Navigation />

      <main className="mx-auto max-w-7xl px-6 pb-16 pt-24 sm:px-8">
        <section className="mb-14">
          <div className="mb-8 inline-flex rounded-full border border-sky-200 bg-white/80 px-4 py-2 text-sm text-sky-700 shadow-sm">
            HeyBlog Public Surface
          </div>
          <h1 className="max-w-4xl text-5xl leading-tight text-slate-950 sm:text-6xl">
            用统一首页浏览博客生态，再切到图谱深入关系网络。
          </h1>
          <p className="mt-5 max-w-3xl text-lg leading-8 text-slate-600">
            当前首页对齐 `frontend_example` 的展示风格，同时接入真实的博客统计、抓取队列状态和 catalog 卡片信息。
          </p>
          <div className="mt-8">
            <SearchBar onSearch={handleSearch} isLoading={isSearching} />
          </div>
        </section>

        <section className="mb-14 grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-[28px] border border-sky-200 bg-white/95 p-6 shadow-[0_18px_40px_rgba(15,23,42,0.08)]">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-sky-500 text-white">
              <Network className="h-6 w-6" />
            </div>
            <div className="text-sm text-slate-500">总节点数</div>
            <div className="mt-2 text-4xl text-slate-950">{stats.totalNodes}</div>
          </div>
          <div className="rounded-[28px] border border-emerald-200 bg-white/95 p-6 shadow-[0_18px_40px_rgba(15,23,42,0.08)]">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-500 text-white">
              <GitBranch className="h-6 w-6" />
            </div>
            <div className="text-sm text-slate-500">总连接数</div>
            <div className="mt-2 text-4xl text-slate-950">{stats.totalEdges}</div>
          </div>
          <div className="rounded-[28px] border border-violet-200 bg-white/95 p-6 shadow-[0_18px_40px_rgba(15,23,42,0.08)]">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-500 text-white">
              <Radar className="h-6 w-6" />
            </div>
            <div className="text-sm text-slate-500">待处理队列</div>
            <div className="mt-2 text-4xl text-slate-950">{status?.pendingTasks ?? 0}</div>
          </div>
          <div className="rounded-[28px] border border-amber-200 bg-white/95 p-6 shadow-[0_18px_40px_rgba(15,23,42,0.08)]">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-500 text-white">
              <TimerReset className="h-6 w-6" />
            </div>
            <div className="text-sm text-slate-500">处理中 / 失败</div>
            <div className="mt-2 text-4xl text-slate-950">
              {(status?.processingTasks ?? 0) + (status?.failedTasks ?? 0)}
            </div>
          </div>
        </section>

        <section className="mb-8 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-wrap gap-3">
            {HOME_STATUS_FILTERS.map((filter) => {
              const isActive = statusFilter === filter;
              return (
                <button
                  key={filter}
                  type="button"
                  onClick={() => handleStatusFilterChange(filter)}
                  className={`rounded-full border px-4 py-2 text-sm transition-colors ${
                    isActive
                      ? "border-sky-500 bg-sky-500 text-white"
                      : "border-slate-200 bg-white text-slate-600 hover:border-sky-300 hover:text-sky-600"
                  }`}
                >
                  {filter}
                </button>
              );
            })}
          </div>
          <div className="flex items-center gap-3 text-sm text-slate-500">
            <span>
              当前显示第 {catalog.page} / {Math.max(catalog.totalPages, 1)} 页，本页 {catalog.items.length} 个，共 {catalog.totalItems} 个博客
            </span>
            {searchQuery ? <span>搜索词: {searchQuery}</span> : null}
            {isRefreshing ? (
              <span className="inline-flex items-center gap-2 text-sky-600">
                <Loader2 className="h-4 w-4 animate-spin" />
                正在刷新
              </span>
            ) : null}
          </div>
        </section>

        <section className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
          {catalog.items.map((blog) => (
            <BlogCard key={blog.id} blog={blog} />
          ))}
        </section>

        <section className="mt-10 flex items-center justify-between gap-4">
          <button
            type="button"
            onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
            disabled={!catalog.hasPrev}
            className="rounded-full border border-slate-200 px-5 py-2 text-sm text-slate-600 transition-colors hover:border-sky-300 hover:text-sky-600 disabled:cursor-not-allowed disabled:border-slate-100 disabled:text-slate-300"
          >
            上一页
          </button>
          <div className="text-sm text-slate-500">
            每页最多 {DEFAULT_PAGE_SIZE} 个
          </div>
          <button
            type="button"
            onClick={() => setCurrentPage((page) => page + 1)}
            disabled={!catalog.hasNext}
            className="rounded-full border border-slate-200 px-5 py-2 text-sm text-slate-600 transition-colors hover:border-sky-300 hover:text-sky-600 disabled:cursor-not-allowed disabled:border-slate-100 disabled:text-slate-300"
          >
            下一页
          </button>
        </section>
      </main>
    </div>
  );
}
