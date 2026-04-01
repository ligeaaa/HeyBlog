import type { GraphNodeDetails } from "../../lib/graph/graphScene";
import type { GraphViewMeta } from "../../lib/api";
import { SiteIdentity } from "../SiteIdentity";

type Props = {
  details: GraphNodeDetails | null;
  lastUpdatedAt: string | null;
  viewMeta: GraphViewMeta | null;
};

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="graph-stat">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

export function GraphInspector({ details, lastUpdatedAt, viewMeta }: Props) {
  return (
    <aside className="graph-panel" aria-live="polite">
      {details ? (
        <>
          <div className="graph-panel-head">
            <p className="eyebrow">Selected Node</p>
            <SiteIdentity
              className="graph-site-identity"
              title={details.title}
              domain={details.domain}
              iconUrl={details.iconUrl}
              nameElement="h3"
            />
          </div>
          <dl className="graph-stat-grid">
            <Stat label="Degree" value={details.degree} />
            <Stat label="Outgoing" value={details.outgoingCount} />
            <Stat label="Incoming" value={details.incomingCount} />
            <Stat label="友链数" value={details.friendLinks} />
            <Stat label="状态" value={details.crawlStatus} />
          </dl>
          <div className="graph-panel-section">
            <p className="eyebrow">URL</p>
            <p className="url-cell">{details.url}</p>
          </div>
        </>
      ) : (
        <div className="graph-panel-empty">
          <p className="eyebrow">Inspector</p>
          <h3>选择一个 blog 节点</h3>
          <p className="page-copy">
            图谱支持拖拽节点、缩放视图，并可通过右上角操作进行刷新、重置核心视图和手动重新布局。
          </p>
        </div>
      )}

      <div className="graph-panel-section graph-panel-meta">
        <p className="eyebrow">Refresh</p>
        <p className="graph-panel-subtle">
          自动刷新：10 分钟
          <br />
          最近同步：{lastUpdatedAt ?? "尚未同步"}
        </p>
      </div>

      {viewMeta ? (
        <div className="graph-panel-section graph-panel-meta">
          <p className="eyebrow">View</p>
          <p className="graph-panel-subtle">
            策略：{viewMeta.strategy}
            <br />
            当前视图：{viewMeta.selected_nodes} nodes / {viewMeta.selected_edges} edges
            <br />
            数据源：{viewMeta.source}
            {viewMeta.snapshot_version ? (
              <>
                <br />
                Snapshot：{viewMeta.snapshot_version}
              </>
            ) : null}
            {viewMeta.sampled ? (
              <>
                <br />
                采样：{viewMeta.sample_mode} / seed={viewMeta.sample_seed}
              </>
            ) : null}
          </p>
        </div>
      ) : null}
    </aside>
  );
}
