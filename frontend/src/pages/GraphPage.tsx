import { useMemo, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { Surface } from "../components/Surface";
import { useGraph } from "../lib/hooks";
import type { BlogRecord, GraphPayload } from "../lib/api";

type GraphNode = BlogRecord & {
  x: number;
  y: number;
};

type HoveredNode = {
  id: number;
  url: string;
  title: string;
  friendLinks: number;
  outgoingCount: number;
  incomingCount: number;
  depth: number;
};

const VIEWPORT_WIDTH = 980;
const VIEWPORT_HEIGHT = 540;
const GRAPH_RADIUS = 210;

function normalizeGraph(payload: GraphPayload | undefined): { nodes: GraphNode[]; edges: GraphPayload["edges"] } {
  const nodeCount = Math.max(payload?.nodes.length ?? 1, 1);
  const nodes = (payload?.nodes ?? []).map((node, index) => {
    const angle = (Math.PI * 2 * index) / nodeCount;
    return {
      ...node,
      x: VIEWPORT_WIDTH / 2 + Math.cos(angle) * GRAPH_RADIUS,
      y: VIEWPORT_HEIGHT / 2 + Math.sin(angle) * GRAPH_RADIUS,
    };
  });

  return {
    nodes,
    edges: payload?.edges ?? [],
  };
}

export function GraphPage() {
  const graph = useGraph();
  const [hovered, setHovered] = useState<HoveredNode | null>(null);

  const normalized = useMemo(() => normalizeGraph(graph.data), [graph.data]);
  const nodeMap = useMemo(() => new Map(normalized.nodes.map((node) => [node.id, node])), [normalized.nodes]);

  const outgoingById = useMemo(() => {
    const counter = new Map<number, number>();
    normalized.edges.forEach((edge) => {
      counter.set(edge.from_blog_id, (counter.get(edge.from_blog_id) ?? 0) + 1);
    });
    return counter;
  }, [normalized.edges]);

  const incomingById = useMemo(() => {
    const counter = new Map<number, number>();
    normalized.edges.forEach((edge) => {
      counter.set(edge.to_blog_id, (counter.get(edge.to_blog_id) ?? 0) + 1);
    });
    return counter;
  }, [normalized.edges]);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Topology"
        title="Blog 友链图谱"
        description="每个 blog 显示为 node，友链显示为 edge。鼠标悬停节点可以查看 URL、标题与关联数量。"
      />
      <Surface title="Graph 视图" note="来自 /api/graph，基于 React + SVG 渲染">
        {graph.isLoading ? <p>正在加载图谱…</p> : null}
        {graph.error ? <p className="error-copy">图谱加载失败：{graph.error.message}</p> : null}
        {!graph.isLoading && !graph.error && normalized.nodes.length === 0 ? <p>暂无图谱数据。</p> : null}

        {normalized.nodes.length > 0 ? (
          <div className="graph-layout">
            <svg
              className="graph-canvas"
              viewBox={`0 0 ${VIEWPORT_WIDTH} ${VIEWPORT_HEIGHT}`}
              role="img"
              aria-label="Blog graph visualization"
            >
              {normalized.edges.map((edge) => {
                const source = nodeMap.get(edge.from_blog_id);
                const target = nodeMap.get(edge.to_blog_id);
                if (!source || !target) {
                  return null;
                }
                return (
                  <line
                    key={edge.id}
                    x1={source.x}
                    y1={source.y}
                    x2={target.x}
                    y2={target.y}
                    className="graph-edge"
                  />
                );
              })}

              {normalized.nodes.map((node) => {
                const incoming = incomingById.get(node.id) ?? 0;
                const outgoing = outgoingById.get(node.id) ?? 0;
                const radius = Math.max(8, Math.min(22, 8 + outgoing * 0.9));
                return (
                  <g
                    key={node.id}
                    transform={`translate(${node.x}, ${node.y})`}
                    onMouseEnter={() =>
                      setHovered({
                        id: node.id,
                        url: node.url,
                        title: (node as BlogRecord & { title?: string }).title ?? node.domain,
                        friendLinks: node.friend_links_count,
                        outgoingCount: outgoing,
                        incomingCount: incoming,
                        depth: node.depth,
                      })
                    }
                    onMouseLeave={() => setHovered(null)}
                  >
                    <circle r={radius} className="graph-node" />
                  </g>
                );
              })}
            </svg>
            <aside className="graph-tooltip" aria-live="polite">
              {hovered ? (
                <dl className="detail-grid">
                  <div>
                    <dt>ID</dt>
                    <dd>{hovered.id}</dd>
                  </div>
                  <div>
                    <dt>Title</dt>
                    <dd>{hovered.title}</dd>
                  </div>
                  <div>
                    <dt>URL</dt>
                    <dd className="url-cell">{hovered.url}</dd>
                  </div>
                  <div>
                    <dt>链接 blog 数</dt>
                    <dd>{hovered.friendLinks}</dd>
                  </div>
                  <div>
                    <dt>Outgoing</dt>
                    <dd>{hovered.outgoingCount}</dd>
                  </div>
                  <div>
                    <dt>Incoming</dt>
                    <dd>{hovered.incomingCount}</dd>
                  </div>
                  <div>
                    <dt>Depth</dt>
                    <dd>{hovered.depth}</dd>
                  </div>
                </dl>
              ) : (
                <p className="page-copy">将鼠标移动到任意节点查看详细信息。</p>
              )}
            </aside>
          </div>
        ) : null}
      </Surface>
    </div>
  );
}
