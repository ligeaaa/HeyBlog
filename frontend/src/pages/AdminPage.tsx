import {
  Activity,
  AlertTriangle,
  Database,
  Loader2,
  Play,
  RefreshCcw,
  RotateCcw,
  Shield,
  Square,
  Timer,
  Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Navigation } from "../components/Navigation";
import {
  fetchAdminDedupLatest,
  fetchAdminRuntimeCurrent,
  fetchAdminRuntimeStatus,
  fetchStats,
  postAdminBootstrap,
  postAdminResetDatabase,
  postAdminRunBatch,
  postAdminRuntimeStart,
  postAdminRuntimeStop,
} from "../lib/api";
import type {
  AdminDedupSummary,
  AdminRuntimeCurrent,
  AdminRuntimeStatus,
  StatsData,
} from "../types/graph";

const ADMIN_TOKEN_STORAGE_KEY = "heyblog_admin_token";

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
  const [batchSize, setBatchSize] = useState("10");
  const [isLoading, setIsLoading] = useState(true);
  const [isRunningAction, setIsRunningAction] = useState(false);
  const [adminError, setAdminError] = useState<string | null>(null);

  useEffect(() => {
    void loadAdminPage(activeAdminToken);
  }, [activeAdminToken]);

  /**
   * Load the admin page summary and privileged panels.
   *
   * @param adminToken Admin bearer token used for protected endpoints.
   * @returns Promise resolved after page state updates.
   */
  async function loadAdminPage(adminToken: string) {
    try {
      setIsLoading(true);
      const statsResponse = await fetchStats();
      setStats(statsResponse);

      if (!adminToken.trim()) {
        setRuntimeStatus(null);
        setRuntimeCurrent(null);
        setLatestDedup(null);
        setAdminError("请输入管理员 Token 以加载受保护接口。");
        return;
      }

      const [runtimeStatusResponse, runtimeCurrentResponse, latestDedupResponse] = await Promise.all([
        fetchAdminRuntimeStatus(adminToken),
        fetchAdminRuntimeCurrent(adminToken),
        fetchAdminDedupLatest(adminToken),
      ]);
      setRuntimeStatus(runtimeStatusResponse);
      setRuntimeCurrent(runtimeCurrentResponse);
      setLatestDedup(latestDedupResponse);
      setAdminError(null);
    } catch (error) {
      console.error(error);
      setRuntimeStatus(null);
      setRuntimeCurrent(null);
      setLatestDedup(null);
      setAdminError("管理员接口加载失败，请确认 Token 是否正确。");
    } finally {
      setIsLoading(false);
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
              </div>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
