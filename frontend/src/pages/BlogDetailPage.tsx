import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import { SiteIdentity } from "../components/SiteIdentity";
import { Surface } from "../components/Surface";
import { D3GraphCanvas } from "../components/graph/D3GraphCanvas";
import { GraphInspector } from "../components/graph/GraphInspector";
import { ApiError } from "../lib/api";
import { DEFAULT_GRAPH_VIEWPORT, type GraphRendererHandle } from "../lib/graph/graphRenderer";
import { buildGraphScene, createEmptyGraphOverlay } from "../lib/graph/graphScene";
import { useBlogDetailView, useGraphNeighbors } from "../lib/hooks";

function parseBlogId(rawBlogId: string | undefined) {
  if (!rawBlogId || !/^\d+$/.test(rawBlogId)) {
    return null;
  }
  const parsed = Number(rawBlogId);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

function formatDate(value: string | null) {
  if (!value) {
    return "暂无";
  }
  return new Date(value).toLocaleString();
}

function formatLastUpdated(timestamp: number) {
  if (!timestamp) {
    return null;
  }
  return new Date(timestamp).toLocaleString();
}

function graphLimitForHops(hops: number) {
  if (hops <= 1) {
    return 40;
  }
  if (hops === 2) {
    return 90;
  }
  return 160;
}

export function BlogDetailPage() {
  const { blogId: rawBlogId } = useParams();
  const blogId = parseBlogId(rawBlogId);
  const detailView = useBlogDetailView(blogId);
  const [graphDepth, setGraphDepth] = useState<1 | 2 | 3>(1);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(blogId ? String(blogId) : null);
  const [showRecommendations, setShowRecommendations] = useState(false);
  const rendererRef = useRef<GraphRendererHandle | null>(null);
  const overlayRef = useRef(createEmptyGraphOverlay());
  const graphQuery = useGraphNeighbors({
    blogId,
    hops: graphDepth,
    limit: graphLimitForHops(graphDepth),
    enabled: blogId != null,
  });

  useEffect(() => {
    setSelectedNodeId(blogId ? String(blogId) : null);
    overlayRef.current = createEmptyGraphOverlay();
  }, [blogId]);

  const graphBundle = useMemo(() => buildGraphScene(graphQuery.data, overlayRef.current), [graphQuery.data]);

  useEffect(() => {
    if (blogId == null) {
      return;
    }
    const currentBlogNodeId = String(blogId);
    if (graphBundle.detailsById.has(currentBlogNodeId)) {
      setSelectedNodeId((current) => current ?? currentBlogNodeId);
      return;
    }
    if (selectedNodeId && graphBundle.detailsById.has(selectedNodeId)) {
      return;
    }
    setSelectedNodeId(graphBundle.nodes[0]?.id ?? null);
  }, [blogId, graphBundle.detailsById, graphBundle.nodes, selectedNodeId]);

  useEffect(() => {
    const renderer = rendererRef.current;
    if (!renderer || graphBundle.nodes.length === 0) {
      return;
    }
    renderer.restoreViewport(DEFAULT_GRAPH_VIEWPORT);
    renderer.fitView();
    if (graphBundle.shouldRunLayout) {
      renderer.requestRelayout("soft");
    }
  }, [graphBundle.signature, graphBundle.nodes.length, graphBundle.shouldRunLayout]);

  if (blogId == null) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Blog"
          title="博客详情不可用"
          description="当前路由中的 blogId 无效，无法读取博客详情。"
          actions={
            <div className="page-actions">
              <Link className="secondary-button button-link" to="/blogs">
                返回发现页
              </Link>
            </div>
          }
        />
        <Surface title="参数无效">
          <p>请从博客列表或搜索结果重新进入详情页，路径格式应为 `/blogs/:blogId`。</p>
        </Surface>
      </div>
    );
  }

  if (detailView.isLoading) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow="Blog" title={`博客 #${blogId}`} description="正在加载博客详情与关系线索。" />
        <Surface title="读取中">
          <p>正在获取博客详情、关系图谱与“朋友的朋友”推荐…</p>
        </Surface>
      </div>
    );
  }

  if (detailView.error instanceof ApiError && detailView.error.status === 404) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Blog"
          title="博客不存在"
          description={`系统中没有找到 ID 为 ${blogId} 的博客记录。`}
          actions={
            <div className="page-actions">
              <Link className="secondary-button button-link" to="/search">
                去搜索
              </Link>
              <Link className="secondary-button button-link" to="/blogs">
                返回发现页
              </Link>
            </div>
          }
        />
        <Surface title="未找到记录">
          <p>这条博客记录可能尚未被抓到，或者当前 ID 不存在。</p>
        </Surface>
      </div>
    );
  }

  if (detailView.error || !detailView.blog) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow="Blog" title={`博客 #${blogId}`} description="博客详情加载失败。" />
        <Surface title="请求失败">
          <p className="error-copy">读取失败：{detailView.error?.message ?? "未知错误"}</p>
        </Surface>
      </div>
    );
  }

  const blog = detailView.blog;
  const selectedDetails = selectedNodeId ? graphBundle.detailsById.get(selectedNodeId) ?? null : null;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Blog"
        title={blog.title?.trim() || blog.domain}
        description="详情页现在先展示这条博客的关系图谱，再把“朋友的朋友”放到下方折叠展开，便于先看直连结构再看推荐。"
        actions={
          <div className="page-actions">
            <Link
              className="secondary-button button-link"
              to={`/search?q=${encodeURIComponent(blog.title || blog.domain)}`}
            >
              去搜索
            </Link>
            <Link className="secondary-button button-link" to="/blogs">
              返回发现页
            </Link>
          </div>
        }
      />

      <Surface title="博客名片" note={`Blog ID ${blog.id}`}>
        <div className="blog-detail-hero">
          <SiteIdentity title={blog.title} domain={blog.domain} iconUrl={blog.icon_url} nameElement="h3" />
          <div className="blog-detail-copy">
            <p className="page-copy">{blog.url}</p>
            <p className="meta-copy">
              最近活跃信号 {formatDate(blog.activity_at)} · 关系线索 {blog.connection_count}
            </p>
            <span className={`status-chip status-${blog.crawl_status.toLowerCase()}`}>{blog.crawl_status}</span>
          </div>
        </div>
      </Surface>

      <div className="stats-grid">
        <div className="stat-card">
          <span>入边</span>
          <strong>{blog.incoming_count}</strong>
        </div>
        <div className="stat-card">
          <span>出边</span>
          <strong>{blog.outgoing_count}</strong>
        </div>
        <div className="stat-card">
          <span>连接度</span>
          <strong>{blog.connection_count}</strong>
        </div>
        <div className="stat-card">
          <span>资料完整度</span>
          <strong>{blog.identity_complete ? "完整" : "待补齐"}</strong>
        </div>
      </div>

      <Surface title="关系图谱" note="把“它指向谁”和“谁指向它”合并到一个有向图里；箭头表示指向方向。">
        <div className="graph-layout">
          <div className="graph-workbench">
            <div className="graph-toolbar">
              <div>
                <p className="eyebrow">Relationship Graph</p>
                <p className="graph-toolbar-copy">
                  默认展示当前博客一层邻居，可切换为 2 层或 3 层继续展开。点击节点可查看对应博客的入/出边统计。
                </p>
              </div>
              <div className="graph-toolbar-actions">
                <label className="graph-control graph-control-compact">
                  <span>扩展深度</span>
                  <select
                    aria-label="关系图谱深度"
                    value={graphDepth}
                    onChange={(event) => {
                      const value = Number(event.target.value);
                      setGraphDepth(value === 2 ? 2 : value === 3 ? 3 : 1);
                    }}
                  >
                    <option value={1}>1 层</option>
                    <option value={2}>2 层</option>
                    <option value={3}>3 层</option>
                  </select>
                </label>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={graphQuery.isFetching}
                  onClick={() => {
                    graphQuery.refetch();
                  }}
                >
                  {graphQuery.isFetching ? "刷新中…" : "刷新图谱"}
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => {
                    rendererRef.current?.fitView();
                  }}
                >
                  适配视图
                </button>
              </div>
            </div>

            {graphQuery.isLoading ? <p>正在加载关系图谱…</p> : null}
            {graphQuery.error ? <p className="error-copy">图谱加载失败：{graphQuery.error.message}</p> : null}
            {!graphQuery.isLoading && !graphQuery.error && graphBundle.nodes.length === 0 ? (
              <p>当前还没有可展示的关系图谱数据。</p>
            ) : null}

            {graphBundle.nodes.length > 0 ? (
              <D3GraphCanvas
                ref={rendererRef}
                scene={graphBundle}
                selectedNodeId={selectedNodeId}
                onSelect={setSelectedNodeId}
                onViewportChange={() => undefined}
                onOverlayChange={(overlay) => {
                  overlayRef.current = overlay;
                }}
              />
            ) : null}
          </div>

          <GraphInspector
            details={selectedDetails}
            lastUpdatedAt={formatLastUpdated(graphQuery.dataUpdatedAt)}
            viewMeta={graphQuery.data?.meta ?? null}
          />
        </div>
      </Surface>

      <Surface title="聚合信息" note="先回答“这是什么博客、最近是否活跃、和谁有关”">
        <dl className="detail-grid">
          <div>
            <dt>域名</dt>
            <dd>{blog.domain}</dd>
          </div>
          <div>
            <dt>最近活跃信号</dt>
            <dd>{formatDate(blog.activity_at)}</dd>
          </div>
          <div>
            <dt>最近抓取</dt>
            <dd>{formatDate(blog.last_crawled_at)}</dd>
          </div>
          <div>
            <dt>最近收录</dt>
            <dd>{formatDate(blog.created_at)}</dd>
          </div>
          <div>
            <dt>友链数</dt>
            <dd>{blog.friend_links_count}</dd>
          </div>
          <div>
            <dt>原始 URL</dt>
            <dd className="url-cell">{blog.url}</dd>
          </div>
        </dl>
      </Surface>

      <Surface title="朋友的朋友" note="你的友链认识、但你还没直接认识的博客。默认折叠，避免打断先看图谱。">
        <div className="collapsible-section">
          <div className="collapsible-head">
            <p className="graph-toolbar-copy">
              当前推荐 {blog.recommended_blogs.length} 个候选博客，可作为下一步扩展友链的参考。
            </p>
            <button
              type="button"
              className="secondary-button"
              aria-expanded={showRecommendations}
              onClick={() => {
                setShowRecommendations((current) => !current);
              }}
            >
              {showRecommendations ? "收起推荐" : "展开推荐"}
            </button>
          </div>

          {showRecommendations ? (
            blog.recommended_blogs.length ? (
              <div className="recommendation-grid">
                {blog.recommended_blogs.map((item) => (
                  <article key={item.blog.id} className="recommendation-card">
                    <Link className="card-link" to={`/blogs/${item.blog.id}`}>
                      <SiteIdentity title={item.blog.title} domain={item.blog.domain} iconUrl={item.blog.icon_url} />
                    </Link>
                    <p className="meta-copy">
                      通过 {item.via_blogs.map((viaBlog) => viaBlog.title?.trim() || viaBlog.domain).join("、")} 认识 ·
                      共同线索 {item.mutual_connection_count}
                    </p>
                  </article>
                ))}
              </div>
            ) : (
              <p>当前还没有“朋友的朋友”推荐，说明这条博客的直连关系还比较少，或者它已经和这些博客直接互相认识。</p>
            )
          ) : (
            <p className="page-copy">展开后可查看推荐博客，以及它们是通过哪些共同朋友被连接到当前博客的。</p>
          )}
        </div>
      </Surface>
    </div>
  );
}
