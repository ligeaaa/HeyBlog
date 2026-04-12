import { FormEvent, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { Surface } from "../components/Surface";
import { ResetDatabasePayload } from "../lib/api";
import {
  useBlogDedupScanRunItems,
  useCrawlerActions,
  useLatestBlogDedupScanRun,
  useRunBlogDedupScan,
  useRuntimeStatus,
} from "../lib/hooks";

function formatResetMessage(result: ResetDatabasePayload) {
  const summary = `database reset: blogs=${result.blogs_deleted}, edges=${result.edges_deleted}, logs=${result.logs_deleted}`;
  if (result.search_reindexed) {
    return `${summary}; search index refreshed.`;
  }
  return `${summary}; search reindex failed: ${result.search_error ?? "unknown error"}`;
}

export function ControlPage() {
  const runtime = useRuntimeStatus();
  const actions = useCrawlerActions();
  const scan = useRunBlogDedupScan();
  const latestScan = useLatestBlogDedupScanRun({ refetchInterval: 1000 });
  const latestScanId = latestScan.data?.id ?? null;
  const latestScanItems = useBlogDedupScanRunItems(latestScanId, { enabled: latestScanId != null });
  const [batchCount, setBatchCount] = useState("10");
  const [message, setMessage] = useState("Ready.");
  const runtimeStatus = runtime.data?.runner_status;
  const maintenanceInProgress = runtime.data?.maintenance_in_progress ?? false;
  const scanIsRunning = latestScan.data?.status === "RUNNING";
  const resetBlocked =
    runtime.isLoading ||
    runtimeStatus == null ||
    ["starting", "running", "stopping"].includes(runtimeStatus) ||
    maintenanceInProgress;

  const handleRunBatch = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const maxNodes = Number(batchCount);
      const result = await actions.runBatch.mutateAsync(maxNodes);
      setMessage(`run-batch complete: ${JSON.stringify(result)}`);
    } catch (error) {
      setMessage(`run-batch failed: ${(error as Error).message}`);
    }
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Control"
        title="控制界面"
        description="控制 crawler 开启、关闭，触发新的 N 个 blog 批处理，或在测试开发时重置数据库。"
      />
      <div className="stats-grid">
        <section className="stat-card">
          <span>Runner</span>
          <strong>{runtimeStatus ?? "idle"}</strong>
        </section>
        <section className="stat-card">
          <span>维护模式</span>
          <strong>{maintenanceInProgress ? "进行中" : "关闭"}</strong>
        </section>
        <section className="stat-card">
          <span>最近消息</span>
          <strong className="stat-copy-small">{message}</strong>
        </section>
      </div>
      <Surface title="当前运行态" note="来自 /api/admin/runtime/status" variant="muted">
        <p className="status-line">runner_status: {runtime.data?.runner_status ?? "idle"}</p>
        {maintenanceInProgress ? (
          <p className="error-copy">当前正在执行管理员维护任务，新的运行时启动和批处理会被拒绝。</p>
        ) : null}
        <div className="action-row">
          <button
            className="primary-button"
            disabled={actions.start.isPending || maintenanceInProgress}
            onClick={async () => {
              try {
                const result = await actions.start.mutateAsync();
                setMessage(`start: ${JSON.stringify(result)}`);
              } catch (error) {
                setMessage(`start failed: ${(error as Error).message}`);
              }
            }}
          >
            开启爬虫
          </button>
          <button
            className="secondary-button"
            disabled={actions.stop.isPending || maintenanceInProgress}
            onClick={async () => {
              try {
                const result = await actions.stop.mutateAsync();
                setMessage(`stop: ${JSON.stringify(result)}`);
              } catch (error) {
                setMessage(`stop failed: ${(error as Error).message}`);
              }
            }}
          >
            停止爬虫
          </button>
          <button
            className="secondary-button"
            disabled={actions.bootstrap.isPending || maintenanceInProgress}
            onClick={async () => {
              try {
                const result = await actions.bootstrap.mutateAsync();
                setMessage(`bootstrap: ${JSON.stringify(result)}`);
              } catch (error) {
                setMessage(`bootstrap failed: ${(error as Error).message}`);
              }
            }}
          >
            导入 Seed
          </button>
        </div>
      </Surface>
      <Surface title="Blog 规则重扫" variant="danger">
        <p className="page-copy">
          按当前 `UrlDecisionChain` 对全库已收录 blog URL 重新评估，不重抓网页内容；被新规则过滤的 blog 会连同相关边一起删除。执行时会自动停爬并在结束后按需恢复。
        </p>
        <button
          className="danger-button"
          disabled={scan.isPending || maintenanceInProgress || scanIsRunning}
          onClick={async () => {
            if (!window.confirm("确认按当前 UrlDecisionChain 重扫全库已收录 blog URL 吗？执行期间会阻止新的 runtime 启动和批处理。")) {
              return;
            }
            try {
              const result = await scan.mutateAsync();
              setMessage(
                `blog decision rescan started: scanned=${result.scanned_count}/${result.total_count}, kept=${result.kept_count}, removed=${result.removed_count}`,
              );
            } catch (error) {
              setMessage(`blog decision rescan failed: ${(error as Error).message}`);
            }
          }}
        >
          {scanIsRunning ? "全库规则重扫进行中" : "执行全库规则重扫"}
        </button>
        {latestScan.data ? (
          <div className="page-copy">
            <p>
              扫描进度：已扫描 URL {latestScan.data.scanned_count} / 总共 URL {latestScan.data.total_count}
            </p>
            <p>
              最近一次扫描：status={latestScan.data.status}，scanned={latestScan.data.scanned_count}/
              {latestScan.data.total_count}，kept={latestScan.data.kept_count}，removed=
              {latestScan.data.removed_count}，
              duration_ms={latestScan.data.duration_ms}
            </p>
            <p>
              crawler_restart_attempted={String(latestScan.data.crawler_restart_attempted)}，
              crawler_restart_succeeded={String(latestScan.data.crawler_restart_succeeded)}，
              search_reindexed={String(latestScan.data.search_reindexed)}
            </p>
            {latestScan.data.error_message ? (
              <p className="error-copy">错误：{latestScan.data.error_message}</p>
            ) : null}
          </div>
        ) : null}
        {latestScanItems.data && latestScanItems.data.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>Removed URL</th>
                <th>Reason</th>
                <th>Survivor Basis</th>
              </tr>
            </thead>
            <tbody>
              {latestScanItems.data.map((item) => (
                <tr key={item.id}>
                  <td>{item.removed_url}</td>
                  <td>{item.reason_code}</td>
                  <td>{item.survivor_selection_basis}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </Surface>
      <Surface title="数据库维护" variant="danger">
        <p className="page-copy">
          清空 blogs、edges 数据并同步重建搜索快照；日志不会写入数据库。
        </p>
        {resetBlocked ? (
          <p className="error-copy">请先让 crawler 回到 idle 状态，再执行数据库重置。</p>
        ) : null}
        <button
          className="danger-button"
          disabled={resetBlocked || actions.resetDatabase.isPending}
          onClick={async () => {
            if (!window.confirm("确认重置数据库吗？这会清空当前采集数据。")) {
              return;
            }
            try {
              const result = await actions.resetDatabase.mutateAsync();
              setMessage(formatResetMessage(result));
            } catch (error) {
              setMessage(`database reset failed: ${(error as Error).message}`);
            }
          }}
        >
          重置数据库
        </button>
      </Surface>
      <Surface title="批量爬取 N 个 blog" variant="muted">
        <form className="batch-form" onSubmit={handleRunBatch}>
          <label>
            <span>Max nodes</span>
            <input
              type="number"
              min="1"
              value={batchCount}
              onChange={(event) => setBatchCount(event.target.value)}
            />
          </label>
          <button
            className="primary-button"
            disabled={actions.runBatch.isPending || maintenanceInProgress}
            type="submit"
          >
            爬取新的 N 个 blog
          </button>
        </form>
      </Surface>
      <Surface title="操作结果" variant="muted">
        <p>{message}</p>
      </Surface>
    </div>
  );
}
