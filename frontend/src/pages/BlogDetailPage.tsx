import { Link, useParams } from "react-router-dom";
import { ApiError } from "../lib/api";
import { RelatedEdge, useBlogDetailView } from "../lib/hooks";
import { PageHeader } from "../components/PageHeader";
import { Surface } from "../components/Surface";

function parseBlogId(rawBlogId: string | undefined) {
  if (!rawBlogId || !/^\d+$/.test(rawBlogId)) {
    return null;
  }
  const parsed = Number(rawBlogId);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

function renderNeighborLabel(edge: RelatedEdge, direction: "incoming" | "outgoing") {
  if (edge.neighborBlog) {
    return edge.neighborBlog.domain;
  }
  return direction === "incoming" ? `Blog #${edge.from_blog_id}` : `Blog #${edge.to_blog_id}`;
}

function getNeighborPath(edge: RelatedEdge, direction: "incoming" | "outgoing") {
  const neighborId = direction === "incoming" ? edge.from_blog_id : edge.to_blog_id;
  return edge.neighborBlog ? `/blogs/${neighborId}` : null;
}

function EdgeList({
  edges,
  direction,
  emptyMessage,
}: {
  edges: RelatedEdge[];
  direction: "incoming" | "outgoing";
  emptyMessage: string;
}) {
  if (!edges.length) {
    return <p>{emptyMessage}</p>;
  }

  return (
    <ul className="result-list">
      {edges.map((edge) => {
        const neighborPath = getNeighborPath(edge, direction);
        const label = renderNeighborLabel(edge, direction);

        return (
          <li key={edge.id} className="result-item">
            {neighborPath ? (
              <Link className="result-link" to={neighborPath}>
                {label}
              </Link>
            ) : (
              <p className="result-title">{label}</p>
            )}
            <p className="page-copy">{edge.link_url_raw}</p>
            <p className="meta-copy">
              {edge.link_text || "无链接文本"} · 关系 {edge.from_blog_id} {"->"} {edge.to_blog_id}
            </p>
          </li>
        );
      })}
    </ul>
  );
}

export function BlogDetailPage() {
  const { blogId: rawBlogId } = useParams();
  const blogId = parseBlogId(rawBlogId);
  const detailView = useBlogDetailView(blogId);

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
                返回列表
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
        <PageHeader
          eyebrow="Blog"
          title={`博客 #${blogId}`}
          description="正在加载博客详情与关联关系。"
        />
        <Surface title="读取中">
          <p>正在获取博客详情和双向关系聚合…</p>
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
                返回列表
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
        <PageHeader
          eyebrow="Blog"
          title={`博客 #${blogId}`}
          description="博客详情加载失败。"
        />
        <Surface title="请求失败">
          <p className="error-copy">读取失败：{detailView.error?.message ?? "未知错误"}</p>
        </Surface>
      </div>
    );
  }

  const blog = detailView.blog;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Blog"
        title={blog.domain}
        description="查看单个博客的基础信息、谁指向它，以及它继续指向了谁。"
        actions={
          <div className="page-actions">
            <Link className="secondary-button button-link" to="/search">
              去搜索
            </Link>
            <Link className="secondary-button button-link" to="/blogs">
              返回列表
            </Link>
          </div>
        }
      />

      <Surface title="基础信息" note={`Blog ID ${blog.id}`}>
        <dl className="detail-grid">
          <div>
            <dt>域名</dt>
            <dd>{blog.domain}</dd>
          </div>
          <div>
            <dt>原始 URL</dt>
            <dd className="url-cell">{blog.url}</dd>
          </div>
          <div>
            <dt>抓取状态</dt>
            <dd>
              <span className={`status-chip status-${blog.crawl_status.toLowerCase()}`}>
                {blog.crawl_status}
              </span>
            </dd>
          </div>
          <div>
            <dt>友链数</dt>
            <dd>{blog.friend_links_count}</dd>
          </div>
          <div>
            <dt>最后更新时间</dt>
            <dd>{new Date(blog.updated_at).toLocaleString()}</dd>
          </div>
        </dl>
      </Surface>

      <div className="stats-grid">
        <div className="stat-card">
          <span>入边</span>
          <strong>{detailView.incomingEdges.length}</strong>
        </div>
        <div className="stat-card">
          <span>出边</span>
          <strong>{detailView.outgoingEdges.length}</strong>
        </div>
      </div>

      <Surface title="谁指向它" note="来自 /api/blogs/{blog_id} 的 incoming_edges">
        <EdgeList
          edges={detailView.incomingEdges}
          direction="incoming"
          emptyMessage="当前没有发现其他博客指向它。"
        />
      </Surface>

      <Surface title="它指向谁" note="来自 /api/blogs/{blog_id} 的 outgoing_edges">
        <EdgeList
          edges={detailView.outgoingEdges}
          direction="outgoing"
          emptyMessage="当前没有记录到它向外指向的博客。"
        />
      </Surface>
    </div>
  );
}
