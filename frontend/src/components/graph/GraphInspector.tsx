import type { GraphNodeDetails } from "../../lib/graph/cytoscapeGraph";

type Props = {
  details: GraphNodeDetails | null;
  lastUpdatedAt: string | null;
};

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="graph-stat">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

export function GraphInspector({ details, lastUpdatedAt }: Props) {
  return (
    <aside className="graph-panel" aria-live="polite">
      {details ? (
        <>
          <div className="graph-panel-head">
            <p className="eyebrow">Selected Node</p>
            <h3>{details.label}</h3>
            <p className="graph-panel-subtle">{details.domain}</p>
          </div>
          <dl className="graph-stat-grid">
            <Stat label="Depth" value={details.depth} />
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
            图谱交互由 Cytoscape 驱动。你可以拖拽节点、缩放视图，并用右上角按钮手动刷新或重新布局。
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
    </aside>
  );
}
