import { CheckCircle2, Database, Filter, GitBranch, Loader2, Rss, Sparkles, XCircle } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Navigation } from "../components/Navigation";
import { fetchFilterStats } from "../lib/api";
import type { FilterStatsData } from "../types/graph";

const EMPTY_FILTER_STATS: FilterStatsData = {
  byFilterReason: { raw: 0 },
  ruleDrops: {},
  successSources: {},
  funnel: {
    raw: 0,
    afterRules: 0,
    modelRejected: 0,
    success: 0,
    blogs: 0,
  },
};

/**
 * Format an integer for compact, scan-friendly dashboard display.
 *
 * @param value Numeric count to format.
 * @returns Localized integer string.
 */
function formatCount(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

/**
 * Render the public filter-statistics page driven by `/api/filter-stats`.
 *
 * @returns Filter stats route UI.
 */
export function FilterStatsPage() {
  const [stats, setStats] = useState<FilterStatsData>(EMPTY_FILTER_STATS);
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

  const ruleRows = useMemo(() => {
    return Object.entries(stats.ruleDrops).filter(([, count]) => count > 0);
  }, [stats.ruleDrops]);
  const rssAccepted = stats.successSources.rss ?? 0;
  const modelAccepted = stats.successSources.model ?? 0;
  const unknownAccepted = stats.successSources.unknown ?? 0;
  const mergedCount = Math.max(stats.funnel.success - stats.funnel.blogs, 0);
  const totalKnownSources = rssAccepted + modelAccepted + unknownAccepted;

  return (
    <div className="min-h-screen overflow-x-hidden bg-[linear-gradient(180deg,_#f7fbfa_0%,_#ffffff_42%,_#f6f8fb_100%)]">
      <Navigation />

      <main className="mx-auto max-w-6xl px-6 pb-16 pt-24 sm:px-8">
        <section className="border-b border-slate-200 pb-8">
          <div className="inline-flex items-center gap-2 rounded-md bg-teal-950 px-3 py-2 text-sm text-white">
            <Filter className="h-4 w-4" />
            Filter Stats
          </div>
          <h1 className="mt-5 text-4xl font-semibold text-slate-950">过滤链统计</h1>
          <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-500">
            规则过滤负责减少候选 URL；RSS 与模型是两个并列的成功判定出口。
          </p>
        </section>

        {isLoading ? (
          <section className="mt-8 flex items-center gap-3 rounded-md border border-slate-200 bg-white p-6 text-slate-500 shadow-sm">
            <Loader2 className="h-5 w-5 animate-spin" />
            正在加载过滤统计...
          </section>
        ) : (
          <>
            <section className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-4">
              <MetricCard icon={Database} label="原始候选" value={stats.funnel.raw} />
              <MetricCard icon={GitBranch} label="规则后候选" value={stats.funnel.afterRules} />
              <MetricCard icon={CheckCircle2} label="成功判定 URL" value={stats.funnel.success} />
              <MetricCard icon={Database} label="实际入库博客" value={stats.funnel.blogs} />
            </section>

            <section className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-[1fr_1.15fr]">
              <div className="rounded-md border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                  <Filter className="h-4 w-4" />
                  规则过滤减少量
                </div>
                <div className="mt-5 space-y-3">
                  {ruleRows.length > 0 ? (
                    ruleRows.map(([status, count]) => (
                      <div key={status} className="grid grid-cols-[1fr_auto] gap-4 rounded-md bg-slate-50 px-4 py-3">
                        <div className="min-w-0 break-all text-sm text-slate-700">{status}</div>
                        <div className="text-sm font-semibold tabular-nums text-slate-950">{formatCount(count)}</div>
                      </div>
                    ))
                  ) : (
                    <div className="rounded-md bg-slate-50 px-4 py-3 text-sm text-slate-500">暂无规则过滤减少量</div>
                  )}
                </div>
              </div>

              <div className="rounded-md border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                  <GitBranch className="h-4 w-4" />
                  成功判定分流
                </div>
                <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <DecisionCard
                    icon={Rss}
                    label="RSS 判定为博客"
                    value={rssAccepted}
                    total={Math.max(totalKnownSources, stats.funnel.success)}
                    tone="teal"
                  />
                  <DecisionCard
                    icon={Sparkles}
                    label="模型判定为博客"
                    value={modelAccepted}
                    total={Math.max(totalKnownSources, stats.funnel.success)}
                    tone="indigo"
                  />
                  <DecisionCard
                    icon={XCircle}
                    label="模型判定非博客"
                    value={stats.funnel.modelRejected}
                    total={Math.max(stats.funnel.afterRules, 1)}
                    tone="rose"
                  />
                  <DecisionCard
                    icon={Database}
                    label="入库合并数量"
                    value={mergedCount}
                    total={Math.max(stats.funnel.success, 1)}
                    tone="slate"
                  />
                </div>
                {unknownAccepted > 0 ? (
                  <div className="mt-4 rounded-md bg-amber-50 px-4 py-3 text-sm text-amber-800">
                    另有 {formatCount(unknownAccepted)} 条 success 缺少来源，通常来自旧数据或手工导入。
                  </div>
                ) : null}
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}

/**
 * Render one top-line metric card.
 *
 * @param props Card label, icon, and numeric value.
 * @returns Metric card element.
 */
function MetricCard({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: number }) {
  return (
    <article className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <Icon className="h-4 w-4" />
        {label}
      </div>
      <div className="mt-4 text-3xl font-semibold tabular-nums text-slate-950">{formatCount(value)}</div>
    </article>
  );
}

/**
 * Render one success or rejection branch in the decision split panel.
 *
 * @param props Card label, icon, value, total denominator, and color tone.
 * @returns Decision branch card element.
 */
function DecisionCard({
  icon: Icon,
  label,
  value,
  total,
  tone,
}: {
  icon: LucideIcon;
  label: string;
  value: number;
  total: number;
  tone: "teal" | "indigo" | "rose" | "slate";
}) {
  const percentage = total > 0 ? Math.round((value / total) * 1000) / 10 : 0;
  const toneClass = {
    teal: "bg-teal-50 text-teal-800",
    indigo: "bg-indigo-50 text-indigo-800",
    rose: "bg-rose-50 text-rose-800",
    slate: "bg-slate-100 text-slate-700",
  }[tone];

  return (
    <article className="rounded-md border border-slate-200 p-4">
      <div className={`inline-flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm ${toneClass}`}>
        <Icon className="h-4 w-4" />
        {label}
      </div>
      <div className="mt-4 text-3xl font-semibold tabular-nums text-slate-950">{formatCount(value)}</div>
      <div className="mt-2 text-sm text-slate-500">{percentage}%</div>
    </article>
  );
}
