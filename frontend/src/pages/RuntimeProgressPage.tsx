import { PageHeader } from "../components/PageHeader";
import { Surface } from "../components/Surface";
import { RuntimeWorkerStatus } from "../lib/api";
import { useRuntimeStatus } from "../lib/hooks";

function formatElapsed(seconds: number | null) {
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

function describeWorker(worker: RuntimeWorkerStatus) {
  if (worker.status === "completed") {
    return "刚完成一个 blog，等待下一次领取。";
  }
  if (worker.status === "error") {
    return worker.last_error ?? "worker 执行出错";
  }
  if (worker.current_url) {
    return `正在处理 ${worker.current_url}`;
  }
  return "当前空闲";
}

function WorkerCard({ worker }: { worker: RuntimeWorkerStatus }) {
  return (
    <article className="worker-card">
      <div className="worker-card-head">
        <div>
          <p className="worker-label">{worker.worker_id}</p>
          <h3>{worker.status}</h3>
        </div>
        <span className={`status-chip status-${worker.status.toLowerCase()}`}>{worker.current_stage ?? "idle"}</span>
      </div>
      <p className="worker-summary">{describeWorker(worker)}</p>
      <dl className="worker-metrics">
        <div>
          <dt>当前 blog</dt>
          <dd>{worker.current_blog_id ?? "—"}</dd>
        </div>
        <div>
          <dt>已耗时</dt>
          <dd>{formatElapsed(worker.elapsed_seconds)}</dd>
        </div>
        <div>
          <dt>已处理</dt>
          <dd>{worker.processed}</dd>
        </div>
        <div>
          <dt>失败</dt>
          <dd>{worker.failed}</dd>
        </div>
      </dl>
      {worker.last_error ? <p className="error-copy">最近错误：{worker.last_error}</p> : null}
    </article>
  );
}

export function RuntimeProgressPage() {
  const runtime = useRuntimeStatus();
  const data = runtime.data;
  const workers = data?.workers ?? [];

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Runtime"
        title="爬虫进度面板"
        description="可视化当前有几个 crawler worker 在工作、分别在做什么、处于什么状态，以及已经耗时多少。"
      />
      <div className="stats-grid">
        <section className="stat-card">
          <span>运行状态</span>
          <strong>{data?.runner_status ?? "idle"}</strong>
        </section>
        <section className="stat-card">
          <span>活跃 worker</span>
          <strong>{data ? `${data.active_workers}/${data.worker_count}` : "0/0"}</strong>
        </section>
        <section className="stat-card">
          <span>Run ID</span>
          <strong className="stat-copy-small">{data?.active_run_id ?? "—"}</strong>
        </section>
      </div>
      <Surface title="Worker 列表" note="来自 /api/runtime/status">
        {runtime.isLoading ? <p>正在读取 crawler worker 进度…</p> : null}
        {runtime.error ? <p className="error-copy">读取失败：{runtime.error.message}</p> : null}
        {!runtime.isLoading && !workers.length ? <p>当前没有活动 worker。</p> : null}
        <div className="worker-grid">
          {workers.map((worker) => (
            <WorkerCard key={worker.worker_id} worker={worker} />
          ))}
        </div>
      </Surface>
    </div>
  );
}
