import { Link, useParams } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import { SiteIdentity } from "../components/SiteIdentity";
import { Surface } from "../components/Surface";
import { ApiError } from "../lib/api";
import { RelatedEdge, useBlogDetailView } from "../lib/hooks";

function parseBlogId(rawBlogId: string | undefined) {
  if (!rawBlogId || !/^\d+$/.test(rawBlogId)) {
    return null;
  }
  const parsed = Number(rawBlogId);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

function renderNeighborLabel(edge: RelatedEdge, direction: "incoming" | "outgoing") {
  if (edge.neighborBlog) {
    return edge.neighborBlog.title?.trim() || edge.neighborBlog.domain;
  }
  return direction === "incoming" ? `Blog #${edge.from_blog_id}` : `Blog #${edge.to_blog_id}`;
}

function getNeighborPath(edge: RelatedEdge, direction: "incoming" | "outgoing") {
  const neighborId = direction === "incoming" ? edge.from_blog_id : edge.to_blog_id;
  return edge.neighborBlog ? `/blogs/${neighborId}` : null;
}

function formatDate(value: string | null) {
  if (!value) {
    return "暂无";
  }
  return new Date(value).toLocaleString();
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
          <p>正在获取博客详情、关系聚合与“朋友的朋友”推荐…</p>
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

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Blog"
        title={blog.title?.trim() || blog.domain}
        description="这里展示这个博客的身份、活跃信号、关系线索，以及“朋友的朋友”推荐。"
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

      <Surface title="朋友的朋友" note="粗糙推荐：你的友链认识、但你还没直接认识的博客">
        {blog.recommended_blogs.length ? (
          <div className="recommendation-grid">
            {blog.recommended_blogs.map((item) => (
              <article key={item.blog.id} className="recommendation-card">
                <Link className="card-link" to={`/blogs/${item.blog.id}`}>
                  <SiteIdentity
                    title={item.blog.title}
                    domain={item.blog.domain}
                    iconUrl={item.blog.icon_url}
                  />
                </Link>
                <p className="meta-copy">
                  通过{" "}
                  {item.via_blogs.map((viaBlog) => viaBlog.title?.trim() || viaBlog.domain).join("、")}
                  {" "}认识 · 共同线索 {item.mutual_connection_count}
                </p>
              </article>
            ))}
          </div>
        ) : (
          <p>当前还没有“朋友的朋友”推荐，说明这条博客的直连关系还比较少，或者它已经和这些博客直接互相认识。</p>
        )}
      </Surface>

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
