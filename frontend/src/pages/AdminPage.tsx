import {
  Activity,
  AlertTriangle,
  BarChart3,
  Database,
  Download,
  ExternalLink,
  FileCheck2,
  Loader2,
  Play,
  RefreshCcw,
  RotateCcw,
  Shield,
  Square,
  Timer,
  Trash2,
} from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import { toast } from "sonner";
import { Navigation } from "../components/Navigation";
import {
  downloadAdminBlogLabelParquet,
  fetchAdminBlogLabelCounts,
  fetchAdminBlogLabelingCandidates,
  fetchAdminBlogLabelParquetStatus,
  fetchAdminDedupLatest,
  fetchAdminRuntimeCurrent,
  fetchAdminRuntimeStatus,
  fetchAdminUrlRefilterEvents,
  fetchAdminUrlRefilterLatest,
  fetchStats,
  postAdminBlogLabelTag,
  postAdminBlogLabelParquetRebuild,
  postAdminBlogLabelParquetSync,
  postAdminBootstrap,
  postAdminResetDatabase,
  postAdminRunBatch,
  postAdminRunUrlRefilter,
  postAdminRuntimeStart,
  postAdminRuntimeStop,
  putAdminBlogLabels,
} from "../lib/api";
import type {
  AdminBlogLabelingCandidate,
  AdminBlogLabelTag,
  AdminDedupSummary,
  AdminRuntimeCurrent,
  AdminRuntimeStatus,
  AdminUrlRefilterRun,
  AdminUrlRefilterRunEvent,
  StatsData,
  AdminBlogLabelCounts,
  AdminBlogLabelParquetStatus,
} from "../types/graph";

const ADMIN_TOKEN_STORAGE_KEY = "heyblog_admin_token";
const DEFAULT_LABELS = ["blog", "company", "other", "unknown"] as const;

/**
 * Read the persisted admin token from local storage when available.
 *
 * @returns Stored admin token or an empty string.
 */
function readStoredAdminToken(): string {
  if (typeof window === "undefined") {
    return "";
  }
  return window.localStorage.getItem(ADMIN_TOKEN_STORAGE_KEY) ?? "";
}

/**
 * Persist the admin token for future visits.
 *
 * @param token Token value entered in the admin page.
 */
function storeAdminToken(token: string) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, token);
}

/**
 * Remove the persisted admin token from local storage.
 */
function clearStoredAdminToken() {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(ADMIN_TOKEN_STORAGE_KEY);
}

/**
 * Resolve an icon URL for a labeling card.
 *
 * @param candidate Blog labeling candidate shown in the admin workbench.
 * @returns Candidate icon URL or a deterministic favicon fallback.
 */
function resolveLabelingIconUrl(candidate: AdminBlogLabelingCandidate): string {
  if (candidate.iconUrl) {
    return candidate.iconUrl;
  }
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(candidate.domain)}&sz=64`;
}

/**
 * Render the admin dashboard backed by the current backend admin APIs.
 *
 * @returns Admin page UI.
 */
export function AdminPage() {
  const [adminTokenInput, setAdminTokenInput] = useState(readStoredAdminToken());
  const [activeAdminToken, setActiveAdminToken] = useState(readStoredAdminToken());
  const [stats, setStats] = useState<StatsData>({ totalNodes: 0, totalEdges: 0 });
  const [runtimeStatus, setRuntimeStatus] = useState<AdminRuntimeStatus | null>(null);
  const [runtimeCurrent, setRuntimeCurrent] = useState<AdminRuntimeCurrent | null>(null);
  const [latestDedup, setLatestDedup] = useState<AdminDedupSummary | null>(null);
  const [latestRefilterRun, setLatestRefilterRun] = useState<AdminUrlRefilterRun | null>(null);
  const [refilterEvents, setRefilterEvents] = useState<AdminUrlRefilterRunEvent[]>([]);
  const [labelingCandidates, setLabelingCandidates] = useState<AdminBlogLabelingCandidate[]>([]);
  const [labelTags, setLabelTags] = useState<AdminBlogLabelTag[]>([]);
  const [labelCounts, setLabelCounts] = useState<AdminBlogLabelCounts>({ totalLabeled: 0, byLabel: {} });
  const [labelParquetStatus, setLabelParquetStatus] = useState<AdminBlogLabelParquetStatus | null>(null);
  const [labelingTotalItems, setLabelingTotalItems] = useState(0);
  const [labelingTotalPages, setLabelingTotalPages] = useState(1);
  const [labelingPage, setLabelingPage] = useState(1);
  const [labelingQuery, setLabelingQuery] = useState("");
  const [batchSize, setBatchSize] = useState("10");
  const [isLoading, setIsLoading] = useState(true);
  const [isRunningAction, setIsRunningAction] = useState(false);
  const [isLabelingLoading, setIsLabelingLoading] = useState(false);
  const [isParquetActionRunning, setIsParquetActionRunning] = useState(false);
  const [labelParquetProgress, setLabelParquetProgress] = useState<string | null>(null);
  const [labelingBlogId, setLabelingBlogId] = useState<number | null>(null);
  const [adminError, setAdminError] = useState<string | null>(null);

  useEffect(() => {
    void loadAdminPage(activeAdminToken);
  }, [activeAdminToken]);

  useEffect(() => {
    if (!activeAdminToken.trim()) {
      return undefined;
    }
    const interval = window.setInterval(() => {
      void loadAdminPage(activeAdminToken, { silent: true });
    }, 3000);
    return () => window.clearInterval(interval);
  }, [activeAdminToken]);

  /**
   * Load the admin page summary and privileged panels.
   *
   * @param adminToken Admin bearer token used for protected endpoints.
   * @returns Promise resolved after page state updates.
   */
  async function loadAdminPage(adminToken: string, options?: { silent?: boolean }) {
    try {
      if (!options?.silent) {
        setIsLoading(true);
      }
      const statsResponse = await fetchStats();
      setStats(statsResponse);

      if (!adminToken.trim()) {
        setRuntimeStatus(null);
        setRuntimeCurrent(null);
        setLatestDedup(null);
        setLatestRefilterRun(null);
        setRefilterEvents([]);
        setLabelingCandidates([]);
        setLabelTags([]);
        setLabelCounts({ totalLabeled: 0, byLabel: {} });
        setLabelParquetStatus(null);
        setLabelingTotalItems(0);
        setLabelingTotalPages(1);
        setAdminError("请输入管理员 Token 以加载受保护接口。");
        return;
      }

      const [
        runtimeStatusResponse,
        runtimeCurrentResponse,
        latestDedupResponse,
        latestRefilterResponse,
        labelingPageResponse,
        labelCountResponse,
        labelParquetResponse,
      ] =
        await Promise.all([
          fetchAdminRuntimeStatus(adminToken),
          fetchAdminRuntimeCurrent(adminToken),
          fetchAdminDedupLatest(adminToken),
          fetchAdminUrlRefilterLatest(adminToken),
          loadLabelingCandidates(adminToken),
          fetchAdminBlogLabelCounts(adminToken),
          fetchAdminBlogLabelParquetStatus(adminToken),
        ]);
      setRuntimeStatus(runtimeStatusResponse);
      setRuntimeCurrent(runtimeCurrentResponse);
      setLatestDedup(latestDedupResponse);
      setLatestRefilterRun(latestRefilterResponse);
      setLabelingCandidates(labelingPageResponse.items);
      setLabelTags(labelingPageResponse.availableTags);
      setLabelCounts(labelCountResponse);
      setLabelParquetStatus(labelParquetResponse);
      setLabelingTotalItems(labelingPageResponse.totalItems);
      setLabelingTotalPages(labelingPageResponse.totalPages);
      if (latestRefilterResponse !== null) {
        setRefilterEvents(await fetchAdminUrlRefilterEvents(adminToken, latestRefilterResponse.id));
      } else {
        setRefilterEvents([]);
      }
      setAdminError(null);
    } catch (error) {
      console.error(error);
      setRuntimeStatus(null);
      setRuntimeCurrent(null);
      setLatestDedup(null);
      setLatestRefilterRun(null);
      setRefilterEvents([]);
      setLabelingCandidates([]);
      setLabelTags([]);
      setLabelCounts({ totalLabeled: 0, byLabel: {} });
      setLabelParquetStatus(null);
      setLabelingTotalItems(0);
      setLabelingTotalPages(1);
      setAdminError("管理员接口加载失败，请确认 Token 是否正确。");
    } finally {
      if (!options?.silent) {
        setIsLoading(false);
      }
    }
  }

  /**
   * Load one page of unlabeled blog candidates and ensure the default tags exist.
   *
   * @param adminToken Admin bearer token used for protected endpoints.
   * @returns Labeling page with only the default label tags exposed to the UI.
   */
  async function loadLabelingCandidates(
    adminToken: string,
    options: { page?: number; query?: string } = {},
  ) {
    const page = options.page ?? labelingPage;
    const query = options.query ?? labelingQuery;
    const firstPage = await fetchAdminBlogLabelingCandidates(adminToken, {
      page,
      pageSize: 12,
      q: query.trim() || undefined,
      labeled: false,
      sort: "id_desc",
    });
    const tagsBySlug = new Map(firstPage.availableTags.map((tag) => [tag.slug, tag]));
    const defaultTags = await Promise.all(
      DEFAULT_LABELS.map(async (label) => tagsBySlug.get(label) ?? postAdminBlogLabelTag(adminToken, label)),
    );
    return {
      ...firstPage,
      availableTags: defaultTags,
    };
  }

  /**
   * Refresh only the labeling workbench without disturbing the runtime panels.
   */
  async function refreshLabelingWorkbench(options: { page?: number; query?: string } = {}) {
    if (!activeAdminToken.trim()) {
      toast.error("请先输入管理员 Token。");
      return;
    }
    try {
      setIsLabelingLoading(true);
      const response = await loadLabelingCandidates(activeAdminToken, options);
      setLabelingCandidates(response.items);
      setLabelTags(response.availableTags);
      setLabelingTotalItems(response.totalItems);
      setLabelingTotalPages(response.totalPages);
      const [counts, parquetStatus] = await Promise.all([
        fetchAdminBlogLabelCounts(activeAdminToken),
        fetchAdminBlogLabelParquetStatus(activeAdminToken),
      ]);
      setLabelCounts(counts);
      setLabelParquetStatus(parquetStatus);
    } catch (error) {
      console.error(error);
      toast.error("标注台加载失败，请检查 token 或服务状态。");
    } finally {
      setIsLabelingLoading(false);
    }
  }

  /**
   * Apply one of the default labels to a candidate and remove it from the unlabeled queue.
   *
   * @param candidate Blog candidate being labeled.
   * @param tag Label tag selected by the operator.
   * @returns Promise resolved after the label update finishes.
   */
  async function handleApplyCandidateLabel(candidate: AdminBlogLabelingCandidate, tag: AdminBlogLabelTag) {
    if (!activeAdminToken.trim()) {
      toast.error("请先输入管理员 Token。");
      return;
    }
    try {
      setLabelingBlogId(candidate.id);
      await putAdminBlogLabels(activeAdminToken, candidate.id, [tag.id]);
      setLabelingCandidates((current) => current.filter((item) => item.id !== candidate.id));
      setLabelingTotalItems((current) => Math.max(0, current - 1));
      setLabelingTotalPages((current) => Math.max(1, current));
      const counts = await fetchAdminBlogLabelCounts(activeAdminToken);
      const parquetStatus =
        counts.totalLabeled > 0 && counts.totalLabeled % (labelParquetStatus?.batchSize ?? 100) === 0
          ? await postAdminBlogLabelParquetSync(activeAdminToken)
          : await fetchAdminBlogLabelParquetStatus(activeAdminToken);
      setLabelCounts(counts);
      setLabelParquetStatus(parquetStatus);
      setLabelParquetProgress(parquetStatus.message);
      toast.success(`已标注为 ${tag.name}。`);
    } catch (error) {
      console.error(error);
      toast.error("标注写入失败，请检查服务状态。");
    } finally {
      setLabelingBlogId(null);
    }
  }

  /**
   * Submit the labeling search form and reload the first result page.
   *
   * @param event Form submission event.
   */
  function handleLabelingSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLabelingPage(1);
    void refreshLabelingWorkbench({ page: 1 });
  }

  /**
   * Run one parquet export action and surface progress in the labeling workbench.
   *
   * @param action Action callback that checks, syncs, rebuilds, or downloads parquet data.
   * @param progressMessage Message shown while the action is in flight.
   * @returns Promise resolved after the parquet action finishes.
   */
  async function runParquetAction(action: () => Promise<AdminBlogLabelParquetStatus | void>, progressMessage: string) {
    if (!activeAdminToken.trim()) {
      toast.error("请先输入管理员 Token。");
      return;
    }
    try {
      setIsParquetActionRunning(true);
      setLabelParquetProgress(progressMessage);
      const result = await action();
      if (result) {
        setLabelParquetStatus(result);
        setLabelParquetProgress(result.message);
        toast.success(result.message);
      } else {
        setLabelParquetProgress("parquet 文件下载已开始。");
        toast.success("parquet 文件下载已开始。");
      }
      setLabelCounts(await fetchAdminBlogLabelCounts(activeAdminToken));
    } catch (error) {
      console.error(error);
      setLabelParquetProgress("parquet 操作失败，请检查服务状态。");
      toast.error("parquet 操作失败，请检查服务状态。");
    } finally {
      setIsParquetActionRunning(false);
    }
  }

  /**
   * Save the current token input and reload protected panels.
   */
  function handleApplyToken() {
    const normalizedToken = adminTokenInput.trim();
    if (!normalizedToken) {
      toast.error("请先输入管理员 Token。");
      return;
    }
    storeAdminToken(normalizedToken);
    setActiveAdminToken(normalizedToken);
    toast.success("管理员 Token 已应用。");
  }

  /**
   * Clear the current admin token from state and storage.
   */
  function handleClearToken() {
    clearStoredAdminToken();
    setAdminTokenInput("");
    setActiveAdminToken("");
    toast.info("已清除管理员 Token。");
  }

  /**
   * Execute one protected admin action and refresh the dashboard afterwards.
   *
   * @param action Callback invoking the desired protected endpoint.
   * @param successMessage Toast message shown after success.
   * @returns Promise resolved after the action and refresh finish.
   */
  async function runAdminAction(action: () => Promise<unknown>, successMessage: string) {
    if (!activeAdminToken.trim()) {
      toast.error("请先输入管理员 Token。");
      return;
    }
    try {
      setIsRunningAction(true);
      await action();
      toast.success(successMessage);
      await loadAdminPage(activeAdminToken);
    } catch (error) {
      console.error(error);
      toast.error("管理员操作失败，请检查 token 或服务状态。");
    } finally {
      setIsRunningAction(false);
    }
  }

  const avgConnections = stats.totalNodes > 0 ? (stats.totalEdges / stats.totalNodes).toFixed(2) : "0.00";
  const visibleLabelCounts = labelTags.map((tag) => ({
    ...tag,
    count: labelCounts.byLabel[tag.slug] ?? 0,
  }));

  return (
    <div className="min-h-screen overflow-x-hidden bg-[radial-gradient(circle_at_top,_rgba(14,165,233,0.15),_transparent_28%),linear-gradient(180deg,_#f4f7fb_0%,_#f8fbff_48%,_#ffffff_100%)]">
      <Navigation />

      <main className="mx-auto max-w-7xl px-6 pb-16 pt-24 sm:px-8">
        <section className="mb-8 flex flex-col gap-5 rounded-[34px] border border-slate-200 bg-white/92 px-8 py-8 shadow-[0_18px_40px_rgba(15,23,42,0.08)] lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="inline-flex rounded-full bg-slate-900 px-4 py-2 text-sm text-white">Admin Console</div>
            <h1 className="mt-5 text-5xl text-slate-950">管理控制台</h1>
            <p className="mt-4 max-w-3xl text-sm leading-7 text-slate-500">
              当前页面参考 `archive/frontend` 的 admin 信息结构，同时改成直接调用现有 `/api/admin/*`。你可以在这里查看 runtime
              并触发 crawl 维护操作。
            </p>
          </div>

          <div className="w-full max-w-xl rounded-[28px] border border-slate-200 bg-slate-50 p-5">
            <label className="mb-2 block text-sm text-slate-600">管理员 Token</label>
            <div className="flex flex-col gap-3 sm:flex-row">
              <input
                type="password"
                value={adminTokenInput}
                onChange={(event) => setAdminTokenInput(event.target.value)}
                placeholder="Bearer token"
                className="min-w-0 flex-1 rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 focus:border-sky-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={handleApplyToken}
                className="rounded-2xl bg-slate-900 px-5 py-3 text-sm text-white transition-colors hover:bg-sky-600"
              >
                应用
              </button>
              <button
                type="button"
                onClick={handleClearToken}
                className="rounded-2xl border border-slate-200 px-5 py-3 text-sm text-slate-700 transition-colors hover:bg-white"
              >
                清除
              </button>
            </div>
            <p className="mt-3 text-xs text-slate-500">
              该 token 只保存在当前浏览器的 localStorage 中，用于请求 `/api/admin/*`。
            </p>
          </div>
        </section>

        <section className="mb-8 grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-[28px] border border-sky-200 bg-white/95 p-6 shadow-[0_18px_40px_rgba(15,23,42,0.08)]">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-sky-500 text-white">
              <Database className="h-6 w-6" />
            </div>
            <div className="text-sm text-slate-500">总节点数</div>
            <div className="mt-2 text-4xl text-slate-950">{stats.totalNodes}</div>
          </div>
          <div className="rounded-[28px] border border-emerald-200 bg-white/95 p-6 shadow-[0_18px_40px_rgba(15,23,42,0.08)]">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-500 text-white">
              <Activity className="h-6 w-6" />
            </div>
            <div className="text-sm text-slate-500">总连接数</div>
            <div className="mt-2 text-4xl text-slate-950">{stats.totalEdges}</div>
          </div>
          <div className="rounded-[28px] border border-violet-200 bg-white/95 p-6 shadow-[0_18px_40px_rgba(15,23,42,0.08)]">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-500 text-white">
              <Timer className="h-6 w-6" />
            </div>
            <div className="text-sm text-slate-500">平均连接度</div>
            <div className="mt-2 text-4xl text-slate-950">{avgConnections}</div>
          </div>
          <div className="rounded-[28px] border border-amber-200 bg-white/95 p-6 shadow-[0_18px_40px_rgba(15,23,42,0.08)]">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-500 text-white">
              <Shield className="h-6 w-6" />
            </div>
            <div className="text-sm text-slate-500">Runtime 状态</div>
            <div className="mt-2 text-2xl text-slate-950">{runtimeStatus?.runnerStatus ?? "未授权"}</div>
          </div>
        </section>

        <section className="mb-8 rounded-[32px] border border-slate-200 bg-white/95 p-6 shadow-[0_18px_40px_rgba(15,23,42,0.08)]">
          <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h2 className="text-2xl text-slate-950">数据标注台</h2>
              <p className="mt-2 text-sm text-slate-500">
                未标注可训练 URL：{labelingTotalItems}。已标注 URL：{labelCounts.totalLabeled}。
              </p>
            </div>
            <form onSubmit={handleLabelingSearch} className="flex w-full flex-col gap-3 sm:flex-row lg:max-w-xl">
              <input
                type="search"
                value={labelingQuery}
                onChange={(event) => setLabelingQuery(event.target.value)}
                placeholder="按 url、title、domain 搜索"
                className="min-w-0 flex-1 rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 focus:border-sky-500 focus:outline-none"
              />
              <button
                type="submit"
                className="rounded-2xl bg-slate-900 px-5 py-3 text-sm text-white transition-colors hover:bg-sky-600"
              >
                搜索
              </button>
              <button
                type="button"
                onClick={() => void refreshLabelingWorkbench()}
                className="rounded-2xl border border-slate-200 px-5 py-3 text-sm text-slate-700 transition-colors hover:bg-slate-50"
              >
                刷新
              </button>
            </form>
          </div>

          <div className="mb-5 grid grid-cols-1 gap-4 xl:grid-cols-[1fr_1.25fr]">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="mb-3 flex items-center gap-2 text-sm text-slate-700">
                <BarChart3 className="h-4 w-4 text-sky-600" />
                label 实时统计
              </div>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {visibleLabelCounts.map((tag) => (
                  <div key={tag.slug} className="rounded-xl border border-white bg-white px-3 py-3 shadow-sm">
                    <div className="truncate text-xs text-slate-500">{tag.name}</div>
                    <div className="mt-1 text-2xl text-slate-950">{tag.count}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="flex items-center gap-2 text-sm text-slate-700">
                    <FileCheck2 className="h-4 w-4 text-emerald-600" />
                    parquet 数据
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    已保存 {labelParquetStatus?.savedCount ?? 0} 条 / 有 label {labelParquetStatus?.totalLabeled ?? 0} 条
                    {labelParquetStatus?.missingCount ? `，缺 ${labelParquetStatus.missingCount} 条` : ""}
                  </div>
                </div>
                {isParquetActionRunning ? <Loader2 className="h-5 w-5 animate-spin text-sky-500" /> : null}
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                <button
                  type="button"
                  disabled={isParquetActionRunning}
                  onClick={() =>
                    void runParquetAction(
                      () => postAdminBlogLabelParquetSync(activeAdminToken),
                      `检查中：已保存 ${labelParquetStatus?.savedCount ?? 0} 条数据，总计有 label 的有 ${labelParquetStatus?.totalLabeled ?? 0} 条数据，重新保存中...`,
                    )
                  }
                  className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-700 transition-colors hover:border-emerald-300 hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  检查补齐
                </button>
                <button
                  type="button"
                  disabled={isParquetActionRunning}
                  onClick={() =>
                    void runParquetAction(
                      () => postAdminBlogLabelParquetRebuild(activeAdminToken),
                      "正在重置 parquet 文件并按当前保存流程重新保存...",
                    )
                  }
                  className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-700 transition-colors hover:border-amber-300 hover:bg-amber-50 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  重建 parquet
                </button>
                <button
                  type="button"
                  disabled={isParquetActionRunning}
                  onClick={() =>
                    void runParquetAction(
                      () => downloadAdminBlogLabelParquet(activeAdminToken),
                      "正在准备 parquet 文件下载...",
                    )
                  }
                  className="flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-sm text-white transition-colors hover:bg-sky-600 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <Download className="h-4 w-4" />
                  下载
                </button>
              </div>
              <div className="mt-3 min-h-5 text-xs text-slate-500">
                {labelParquetProgress ?? labelParquetStatus?.message ?? "parquet 文件会在每 100 条标注边界或补齐/重建时保存。"}
              </div>
            </div>
          </div>

          {isLabelingLoading ? (
            <div className="flex items-center gap-3 rounded-3xl border border-dashed border-slate-200 px-5 py-8 text-sm text-slate-500">
              <Loader2 className="h-5 w-5 animate-spin" />
              正在加载标注候选...
            </div>
          ) : labelingCandidates.length === 0 ? (
            <div className="rounded-3xl border border-dashed border-slate-200 px-5 py-8 text-sm text-slate-500">
              暂无可标注候选。请确认管理员 Token，或调整搜索条件后刷新。
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {labelingCandidates.map((candidate) => (
                <article
                  key={candidate.id}
                  className="flex min-h-[260px] flex-col rounded-[28px] border border-slate-200 bg-slate-50 p-5"
                >
                  <div className="flex flex-1 gap-4">
                    <img
                      src={resolveLabelingIconUrl(candidate)}
                      alt=""
                      className="h-14 w-14 flex-shrink-0 rounded-2xl border border-white bg-white object-contain p-2 shadow-sm"
                      loading="lazy"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="line-clamp-2 text-lg leading-6 text-slate-950">
                        {candidate.title?.trim() || "Untitled"}
                      </div>
                      <a
                        href={candidate.url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-3 flex items-start gap-2 break-all text-sm leading-6 text-sky-700 hover:text-sky-900"
                      >
                        <span>{candidate.url}</span>
                        <ExternalLink className="mt-1 h-3.5 w-3.5 flex-shrink-0" />
                      </a>
                      <div className="mt-3 text-xs text-slate-500">id: {candidate.id}</div>
                    </div>
                  </div>

                  <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
                    {labelTags.map((tag) => {
                      const isActive = candidate.labelSlugs.includes(tag.slug);
                      const isSaving = labelingBlogId === candidate.id;
                      return (
                        <button
                          key={tag.slug}
                          type="button"
                          disabled={isSaving}
                          onClick={() => void handleApplyCandidateLabel(candidate, tag)}
                          className={[
                            "rounded-2xl px-3 py-2.5 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-60",
                            isActive
                              ? "bg-slate-900 text-white"
                              : "border border-slate-200 bg-white text-slate-700 hover:border-sky-300 hover:bg-sky-50",
                          ].join(" ")}
                        >
                          {isSaving ? "..." : tag.name}
                        </button>
                      );
                    })}
                  </div>
                </article>
              ))}
            </div>
          )}

          <div className="mt-5 flex items-center justify-between text-sm text-slate-500">
            <span>
              第 {labelingPage} / {labelingTotalPages} 页
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={labelingPage <= 1 || isLabelingLoading}
                onClick={() => {
                  const nextPage = Math.max(1, labelingPage - 1);
                  setLabelingPage(nextPage);
                  void refreshLabelingWorkbench({ page: nextPage });
                }}
                className="rounded-2xl border border-slate-200 px-4 py-2 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                上一页
              </button>
              <button
                type="button"
                disabled={labelingPage >= labelingTotalPages || labelingCandidates.length === 0 || isLabelingLoading}
                onClick={() => {
                  const nextPage = Math.min(labelingTotalPages, labelingPage + 1);
                  setLabelingPage(nextPage);
                  void refreshLabelingWorkbench({ page: nextPage });
                }}
                className="rounded-2xl border border-slate-200 px-4 py-2 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                下一页
              </button>
            </div>
          </div>
        </section>

        <section className="mb-8 grid grid-cols-1 gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-[32px] border border-slate-200 bg-white/95 p-6 shadow-[0_18px_40px_rgba(15,23,42,0.08)]">
            <div className="mb-6 flex items-center justify-between">
              <div>
                <h2 className="text-2xl text-slate-950">维护操作</h2>
                <p className="mt-2 text-sm text-slate-500">这些按钮直接映射当前 backend 管理接口。</p>
              </div>
              {isRunningAction ? <Loader2 className="h-5 w-5 animate-spin text-sky-500" /> : null}
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <button
                type="button"
                onClick={() => void runAdminAction(() => postAdminBootstrap(activeAdminToken), "种子导入已触发。")}
                className="flex items-center gap-3 rounded-3xl border border-slate-200 px-5 py-4 text-left transition-colors hover:border-sky-300 hover:bg-sky-50"
              >
                <RefreshCcw className="h-5 w-5 text-sky-600" />
                <div>
                  <div className="text-slate-900">导入种子</div>
                  <div className="text-xs text-slate-500">POST /api/admin/crawl/bootstrap</div>
                </div>
              </button>
              <button
                type="button"
                onClick={() =>
                  void runAdminAction(() => postAdminRuntimeStart(activeAdminToken), "后台 crawler 已启动。")
                }
                className="flex items-center gap-3 rounded-3xl border border-slate-200 px-5 py-4 text-left transition-colors hover:border-emerald-300 hover:bg-emerald-50"
              >
                <Play className="h-5 w-5 text-emerald-600" />
                <div>
                  <div className="text-slate-900">启动 runtime</div>
                  <div className="text-xs text-slate-500">POST /api/admin/runtime/start</div>
                </div>
              </button>
              <button
                type="button"
                onClick={() =>
                  void runAdminAction(() => postAdminRuntimeStop(activeAdminToken), "已请求 crawler 安全停止。")
                }
                className="flex items-center gap-3 rounded-3xl border border-slate-200 px-5 py-4 text-left transition-colors hover:border-amber-300 hover:bg-amber-50"
              >
                <Square className="h-5 w-5 text-amber-600" />
                <div>
                  <div className="text-slate-900">停止 runtime</div>
                  <div className="text-xs text-slate-500">POST /api/admin/runtime/stop</div>
                </div>
              </button>
              <div className="rounded-3xl border border-slate-200 px-5 py-4">
                <div className="mb-3 flex items-center justify-between">
                  <div>
                    <div className="text-slate-900">同步跑批</div>
                    <div className="text-xs text-slate-500">POST /api/admin/runtime/run-batch</div>
                  </div>
                  <input
                    type="number"
                    min={1}
                    value={batchSize}
                    onChange={(event) => setBatchSize(event.target.value)}
                    className="w-20 rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none"
                  />
                </div>
                <button
                  type="button"
                  onClick={() =>
                    void runAdminAction(
                      () => postAdminRunBatch(activeAdminToken, Number.parseInt(batchSize, 10) || 10),
                      "同步 crawl batch 已执行。",
                    )
                  }
                  className="rounded-2xl bg-slate-900 px-4 py-2 text-sm text-white transition-colors hover:bg-sky-600"
                >
                  运行 batch
                </button>
              </div>
              <button
                type="button"
                onClick={() =>
                  void runAdminAction(() => postAdminResetDatabase(activeAdminToken), "数据库重置已完成。")
                }
                className="flex items-center gap-3 rounded-3xl border border-rose-200 px-5 py-4 text-left transition-colors hover:bg-rose-50"
              >
                <Trash2 className="h-5 w-5 text-rose-600" />
                <div>
                  <div className="text-slate-900">重置数据库</div>
                  <div className="text-xs text-slate-500">POST /api/admin/database/reset</div>
                </div>
              </button>
              <button
                type="button"
                onClick={() =>
                  void runAdminAction(
                    () => postAdminRunUrlRefilter(activeAdminToken),
                    "重新过滤任务已启动。",
                  )
                }
                className="flex items-center gap-3 rounded-3xl border border-indigo-200 px-5 py-4 text-left transition-colors hover:bg-indigo-50"
              >
                <RotateCcw className="h-5 w-5 text-indigo-600" />
                <div>
                  <div className="text-slate-900">从 raw 重新过滤</div>
                  <div className="text-xs text-slate-500">POST /api/admin/url-refilter-runs</div>
                </div>
              </button>
            </div>
          </div>

          <div className="rounded-[32px] border border-slate-200 bg-white/95 p-6 shadow-[0_18px_40px_rgba(15,23,42,0.08)]">
            <h2 className="text-2xl text-slate-950">受保护状态</h2>
            {isLoading ? (
              <div className="mt-6 flex items-center gap-3 text-sm text-slate-500">
                <Loader2 className="h-5 w-5 animate-spin" />
                加载管理员接口中...
              </div>
            ) : adminError ? (
              <div className="mt-6 rounded-3xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0" />
                  <span>{adminError}</span>
                </div>
              </div>
            ) : (
              <div className="mt-6 space-y-4">
                <div className="rounded-3xl bg-slate-50 p-4">
                  <div className="text-sm text-slate-500">runtime status</div>
                  <div className="mt-1 text-xl text-slate-950">{runtimeStatus?.runnerStatus ?? "-"}</div>
                  <div className="mt-3 grid grid-cols-2 gap-3 text-sm text-slate-600">
                    <div>active workers: {runtimeStatus?.activeWorkers ?? 0}</div>
                    <div>worker count: {runtimeStatus?.workerCount ?? 0}</div>
                    <div>maintenance: {runtimeStatus?.maintenanceInProgress ? "yes" : "no"}</div>
                    <div>current blog id: {runtimeStatus?.currentBlogId ?? "-"}</div>
                  </div>
                </div>
                <div className="rounded-3xl bg-slate-50 p-4">
                  <div className="text-sm text-slate-500">current worker</div>
                  <div className="mt-1 text-xl text-slate-950">{runtimeCurrent?.currentUrl ?? "当前空闲"}</div>
                  <div className="mt-3 text-sm leading-7 text-slate-600">
                    stage: {runtimeCurrent?.currentStage ?? "-"}
                    <br />
                    elapsed: {runtimeCurrent?.elapsedSeconds ?? "-"}s
                    <br />
                    active run: {runtimeCurrent?.activeRunId ?? "-"}
                  </div>
                </div>
                <div className="rounded-3xl bg-slate-50 p-4">
                  <div className="text-sm text-slate-500">latest dedup scan</div>
                  <div className="mt-1 text-xl text-slate-950">{latestDedup?.status ?? "暂无记录"}</div>
                  <div className="mt-3 text-sm leading-7 text-slate-600">
                    run id: {latestDedup?.id ?? "-"}
                    <br />
                    scanned / total: {latestDedup ? `${latestDedup.scannedCount} / ${latestDedup.totalCount}` : "-"}
                    <br />
                    removed: {latestDedup?.removedCount ?? "-"}
                  </div>
                </div>
                <div className="rounded-3xl bg-slate-50 p-4">
                  <div className="text-sm text-slate-500">latest refilter run</div>
                  <div className="mt-1 text-xl text-slate-950">{latestRefilterRun?.status ?? "暂无记录"}</div>
                  <div className="mt-3 text-sm leading-7 text-slate-600">
                    run id: {latestRefilterRun?.id ?? "-"}
                    <br />
                    scanned / total:{" "}
                    {latestRefilterRun ? `${latestRefilterRun.scannedCount} / ${latestRefilterRun.totalCount}` : "-"}
                    <br />
                    activated / deactivated / retagged:{" "}
                    {latestRefilterRun
                      ? `${latestRefilterRun.activatedCount} / ${latestRefilterRun.deactivatedCount} / ${latestRefilterRun.retaggedCount}`
                      : "-"}
                    <br />
                    backup: {latestRefilterRun?.backupPath ?? "-"}
                  </div>
                </div>
                <div className="rounded-3xl bg-slate-50 p-4">
                  <div className="flex items-center justify-between">
                    <div className="text-sm text-slate-500">重新过滤日志</div>
                    <div className="text-xs text-slate-400">{refilterEvents.length} 条</div>
                  </div>
                  <div className="mt-3 max-h-80 space-y-2 overflow-y-auto pr-1 text-sm text-slate-600">
                    {refilterEvents.length === 0 ? (
                      <div className="rounded-2xl border border-dashed border-slate-200 bg-white px-4 py-3 text-slate-400">
                        暂无日志
                      </div>
                    ) : (
                      refilterEvents.map((event) => (
                        <div key={event.id} className="rounded-2xl bg-white px-4 py-3 shadow-sm">
                          <div className="text-xs text-slate-400">{event.createdAt ?? "-"}</div>
                          <div className="mt-1 leading-6 text-slate-700">{event.message}</div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
