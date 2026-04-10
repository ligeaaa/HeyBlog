import { PageHeader } from "../components/PageHeader";
import { Surface } from "../components/Surface";
import { useRuntimeCurrent, useRuntimeStatus } from "../lib/hooks";

function formatElapsed(seconds: number | null | undefined) {
  if (seconds == null) {
    return "—";
  }
  if (seconds < 60) {
    return Number.isInteger(seconds) ? `${seconds}s` : `${seconds.toFixed(1)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60);
  return `${minutes}m ${remainingSeconds}s`;
}

export function CurrentRuntimePage() {
  const current = useRuntimeCurrent();
  const status = useRuntimeStatus();

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Runtime"
        title="当前正在处理的 URL"
        description="观察 crawler 运行器当前是否正在处理某个 blog，以及它处于哪个阶段。"
      />
      <Surface title="当前任务" note="来自 /api/admin/runtime/current">
        {current.isLoading ? <p>正在读取当前处理状态…</p> : null}
        {current.error ? <p className="error-copy">读取失败：{current.error.message}</p> : null}
        <dl className="detail-grid">
          <div>
            <dt>当前 worker</dt>
            <dd>{current.data?.current_worker_id ?? "—"}</dd>
          </div>
          <div>
            <dt>运行状态</dt>
            <dd>{current.data?.runner_status ?? "idle"}</dd>
          </div>
          <div>
            <dt>活跃 worker</dt>
            <dd>
              {current.data?.active_workers ?? 0} / {current.data?.worker_count ?? 0}
            </dd>
          </div>
          <div>
            <dt>当前 URL</dt>
            <dd>{current.data?.current_url ?? "当前没有活动任务"}</dd>
          </div>
          <div>
            <dt>当前阶段</dt>
            <dd>{current.data?.current_stage ?? "idle"}</dd>
          </div>
          <div>
            <dt>已耗时</dt>
            <dd>{formatElapsed(current.data?.elapsed_seconds)}</dd>
          </div>
          <div>
            <dt>Run ID</dt>
            <dd>{current.data?.active_run_id ?? "—"}</dd>
          </div>
        </dl>
      </Surface>
      <Surface title="运行器快照" note="来自 /api/admin/runtime/status">
        {status.isLoading ? <p>正在加载运行器快照…</p> : null}
        <pre className="runtime-json">
          {JSON.stringify(status.data ?? { runner_status: "idle" }, null, 2)}
        </pre>
      </Surface>
    </div>
  );
}
