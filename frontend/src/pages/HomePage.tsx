import { Loader2, Network, GitBranch } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Navigation } from "../components/Navigation";
import { fetchStats } from "../lib/api";
import type { StatsData } from "../types/graph";

const HOME_REFRESH_INTERVAL_MS = 5000;

/**
 * Render the public home page summary without the status-filtered blog catalog.
 *
 * @returns Home route UI.
 */
export function HomePage() {
  const [stats, setStats] = useState<StatsData>({ totalNodes: 0, totalEdges: 0 });
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
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
