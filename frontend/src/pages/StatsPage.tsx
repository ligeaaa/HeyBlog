import { PageHeader } from "../components/PageHeader";
import { StatCard } from "../components/StatCard";
import { Surface } from "../components/Surface";
import { useStats, useStatus } from "../lib/hooks";

export function StatsPage() {
  const status = useStatus();
  const stats = useStats();

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Overview"
        title="统计信息总览"
        description="查看当前图谱规模、处理进度和友链建立情况。"
      />
      {status.error || stats.error ? (
        <p className="error-copy">
          统计信息加载失败：{status.error?.message ?? stats.error?.message}
        </p>
      ) : null}
      <div className="stats-grid">
        <StatCard label="总 blog 数量" value={status.data?.total_blogs ?? 0} />
        <StatCard label="已处理数量" value={status.data?.finished_tasks ?? 0} />
        <StatCard label="正在处理数量" value={status.data?.processing_tasks ?? 0} />
        <StatCard label="已建立 edge 数量" value={status.data?.total_edges ?? 0} />
      </div>
      <Surface title="更详细的统计" note="来自 /api/stats">
        <dl className="detail-grid">
          <div>
            <dt>待处理</dt>
            <dd>{stats.data?.pending_tasks ?? 0}</dd>
          </div>
          <div>
            <dt>失败数量</dt>
            <dd>{stats.data?.failed_tasks ?? 0}</dd>
          </div>
          <div>
            <dt>最大深度</dt>
            <dd>{stats.data?.max_depth ?? 0}</dd>
          </div>
          <div>
            <dt>平均友链数</dt>
            <dd>{Number(stats.data?.average_friend_links ?? 0).toFixed(2)}</dd>
          </div>
        </dl>
      </Surface>
    </div>
  );
}
