import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Navigation } from "../components/Navigation";
import { fetchFilterStats } from "../lib/api";
import type { FilterStatsData } from "../types/graph";

/**
 * Render the public filter-statistics page driven by `/api/filter-stats`.
 *
 * @returns Filter stats route UI.
 */
export function FilterStatsPage() {
  const [stats, setStats] = useState<FilterStatsData>({ byFilterReason: { raw: 0 } });
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    void loadFilterStats();
  }, []);

  /**
   * Load the ordered filter statistics payload.
   *
   * @returns Promise resolved after state updates.
   */
  async function loadFilterStats() {
    try {
      setIsLoading(true);
      setStats(await fetchFilterStats());
    } catch {
      toast.error("过滤统计加载失败，请稍后重试。");
    } finally {
      setIsLoading(false);
    }
  }

  const stages = Object.entries(stats.byFilterReason);

  return (
    <div className="min-h-screen overflow-x-hidden bg-[radial-gradient(circle_at_top,_rgba(15,118,110,0.12),_transparent_30%),linear-gradient(180deg,_#f6fbfb_0%,_#fcfdfd_45%,_#ffffff_100%)]">
      <Navigation />

      <main className="mx-auto max-w-6xl px-6 pb-16 pt-24 sm:px-8">
        <section className="rounded-[34px] border border-slate-200 bg-white/92 px-8 py-8 shadow-[0_18px_40px_rgba(15,23,42,0.08)]">
          <div className="inline-flex rounded-full bg-teal-900 px-4 py-2 text-sm text-white">Filter Stats</div>
          <h1 className="mt-5 text-5xl text-slate-950">过滤链统计</h1>
          <p className="mt-4 max-w-3xl text-sm leading-7 text-slate-500">
            页面按过滤链配置顺序展示每一步执行后还剩多少标准化 URL。
          </p>
        </section>

        {isLoading ? (
          <section className="mt-8 flex items-center gap-3 rounded-[28px] border border-slate-200 bg-white/90 p-6 text-slate-500 shadow-[0_18px_40px_rgba(15,23,42,0.08)]">
            <Loader2 className="h-5 w-5 animate-spin" />
            正在加载过滤统计...
          </section>
        ) : (
          <section className="mt-8 grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
            {stages.map(([status, count], index) => {
              const previousCount = index === 0 ? count : stages[index - 1][1];
              const droppedCount = index === 0 ? 0 : Math.max(previousCount - count, 0);
              return (
                <article
                  key={status}
                  className="rounded-[28px] border border-slate-200 bg-white/95 p-6 shadow-[0_18px_40px_rgba(15,23,42,0.08)]"
                >
                  <div className="text-sm text-slate-500">{index === 0 ? "原始数量" : "过滤后剩余"}</div>
                  <h2 className="mt-2 break-all text-lg text-slate-950">{status}</h2>
                  <div className="mt-4 text-4xl text-slate-950">{count}</div>
                  <div className="mt-3 text-sm text-slate-500">
                    {index === 0 ? "所有进入过滤链的标准化 URL" : `较上一阶段减少 ${droppedCount}`}
                  </div>
                </article>
              );
            })}
          </section>
        )}
      </main>
    </div>
  );
}
