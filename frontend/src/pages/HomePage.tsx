import { GitBranch, Loader2, Network, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Navigation } from "../components/Navigation";
import { fetchBlogsCatalog, fetchStats } from "../lib/api";
import type { BlogCatalogItem, StatsData } from "../types/graph";

const HOME_REFRESH_INTERVAL_MS = 5000;
const HOME_SEARCH_PAGE_SIZE = 30;

/**
 * Render the public home page summary without the status-filtered blog catalog.
 *
 * @returns Home route UI.
 */
export function HomePage() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<StatsData>({ totalNodes: 0, totalEdges: 0 });
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [searchInput, setSearchInput] = useState("");
  const [searchResults, setSearchResults] = useState<BlogCatalogItem[]>([]);
  const [searchTotalItems, setSearchTotalItems] = useState(0);
  const [lastSearchQuery, setLastSearchQuery] = useState("");
  const [hasSearched, setHasSearched] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const refreshInFlightRef = useRef(false);
  const hasLoadedOnceRef = useRef(false);

  useEffect(() => {
    const isFirstLoad = !hasLoadedOnceRef.current;
    if (isFirstLoad) {
      hasLoadedOnceRef.current = true;
    }
    void loadHomePage({
      showInitialLoading: isFirstLoad,
      showRefreshState: !isFirstLoad,
    });
  }, []);

  useEffect(() => {
    let isDisposed = false;

    async function refreshFromTimer() {
      if (document.visibilityState !== "visible" || isDisposed) {
        return;
      }
      await loadHomePage({
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
  }, []);

  /**
   * Load the home page summary metrics.
   *
   * @param options Loading behavior flags.
   * @returns Promise resolved when the homepage state finishes updating.
   */
  async function loadHomePage(options?: {
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

    refreshInFlightRef.current = true;
    try {
      if (showInitialLoading) {
        setIsInitialLoading(true);
      }
      if (showRefreshState) {
        setIsRefreshing(true);
      }
      const statsResponse = await fetchStats();
      setStats(statsResponse);
    } catch {
      if (showErrorToast) {
        toast.error("首页数据加载失败，请刷新页面重试。");
      }
    } finally {
      refreshInFlightRef.current = false;
      setIsInitialLoading(false);
      setIsRefreshing(false);
    }
  }

  /**
   * Search accepted blogs by URL using the server-side normalized URL fuzzy filter.
   *
   * @param event Search form submit event.
   * @returns Promise resolved after results are rendered.
   */
  async function handleSearchSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = searchInput.trim();
    if (!query) {
      setHasSearched(false);
      setLastSearchQuery("");
      setSearchResults([]);
      setSearchTotalItems(0);
      return;
    }

    setIsSearching(true);
    try {
      const page = await fetchBlogsCatalog({
        page: 1,
        pageSize: HOME_SEARCH_PAGE_SIZE,
        url: query,
        sort: "id_desc",
      });
      setSearchResults(page.items);
      setSearchTotalItems(page.totalItems);
      setLastSearchQuery(query);
      setHasSearched(true);
    } catch {
      toast.error("博客搜索失败，请稍后重试。");
    } finally {
      setIsSearching(false);
    }
  }

  /**
   * Navigate to the temporary blog detail route.
   *
   * @param blog Selected search result.
   */
  function openBlogDetail(blog: BlogCatalogItem) {
    navigate(`/blogs/${blog.id}`);
  }

  if (isInitialLoading) {
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
          <h1 className="max-w-4xl text-5xl leading-tight text-slate-950 sm:text-6xl">
            HeyBlog!
          </h1>
          <p className="mt-5 max-w-3xl text-lg leading-8 text-slate-600">
            基于友链爬取所有博客！
          </p>
        </section>

        <section className="mx-auto mb-14 w-full max-w-4xl">
          <form onSubmit={handleSearchSubmit} className="relative">
            <label htmlFor="home-blog-url-search" className="sr-only">
              搜索博客链接
            </label>
            <input
              id="home-blog-url-search"
              type="text"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="输入你的博客链接，看看你的博客有没有被找到吧！"
              disabled={isSearching}
              className="w-full rounded-lg border border-slate-300 bg-white px-5 py-4 pr-14 text-base text-slate-950 shadow-sm outline-none transition-colors placeholder:text-slate-400 focus:border-sky-500 focus:ring-2 focus:ring-sky-100 disabled:cursor-not-allowed disabled:bg-slate-50"
            />
            <button
              type="submit"
              aria-label="搜索博客"
              disabled={isSearching || !searchInput.trim()}
              className="absolute right-2 top-1/2 inline-flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-md bg-sky-500 text-white transition-colors hover:bg-sky-600 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {isSearching ? <Loader2 className="h-5 w-5 animate-spin" /> : <Search className="h-5 w-5" />}
            </button>
          </form>

          {hasSearched ? (
            <div className="mt-4 rounded-lg border border-slate-200 bg-white shadow-sm">
              <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3 text-sm text-slate-500">
                <span>搜索结果</span>
                <span>{searchTotalItems} 个匹配</span>
              </div>
              {searchResults.length > 0 ? (
                <div className="max-h-80 overflow-y-auto">
                  {searchResults.map((blog) => (
                    <button
                      key={blog.id}
                      type="button"
                      onClick={() => openBlogDetail(blog)}
                      className="block w-full border-b border-slate-100 px-4 py-4 text-left transition-colors last:border-b-0 hover:bg-sky-50 focus:bg-sky-50 focus:outline-none"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <div className="truncate text-base text-slate-950">{blog.title || blog.domain}</div>
                          <div className="mt-1 truncate text-sm text-slate-500">{blog.normalizedUrl}</div>
                        </div>
                        <span className="flex-shrink-0 rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-500">
                          {blog.crawlStatus}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="px-4 py-6 text-sm text-slate-500">未找到与 {lastSearchQuery} 匹配的博客。</div>
              )}
            </div>
          ) : null}
        </section>

        <section className="mb-14 grid grid-cols-1 gap-5 md:grid-cols-2">
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
        </section>

        <section className="flex items-center justify-end text-sm text-slate-500">
          {isRefreshing ? (
            <span className="inline-flex items-center gap-2 text-sky-600">
              <Loader2 className="h-4 w-4 animate-spin" />
              正在刷新
            </span>
          ) : null}
        </section>
      </main>
    </div>
  );
}
