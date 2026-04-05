import { FormEvent, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { Surface } from "../components/Surface";
import { ResetDatabasePayload } from "../lib/api";
import { useCrawlerActions, useRuntimeStatus } from "../lib/hooks";

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
  const [batchCount, setBatchCount] = useState("10");
  const [message, setMessage] = useState("Ready.");
  const runtimeStatus = runtime.data?.runner_status;
  const resetBlocked =
    runtime.isLoading ||
    runtimeStatus == null ||
    ["starting", "running", "stopping"].includes(runtimeStatus);

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
      <Surface title="当前运行态" note="来自 /api/runtime/status">
        <p className="status-line">runner_status: {runtime.data?.runner_status ?? "idle"}</p>
        <div className="action-row">
          <button
            className="primary-button"
            disabled={actions.start.isPending}
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
            disabled={actions.stop.isPending}
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
            disabled={actions.bootstrap.isPending}
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
      <Surface title="数据库维护">
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
      <Surface title="批量爬取 N 个 blog">
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
          <button className="primary-button" disabled={actions.runBatch.isPending} type="submit">
            爬取新的 N 个 blog
          </button>
        </form>
      </Surface>
      <Surface title="操作结果">
        <p>{message}</p>
      </Surface>
    </div>
  );
}
