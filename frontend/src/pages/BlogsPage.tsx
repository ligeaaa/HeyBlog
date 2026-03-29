import { PageHeader } from "../components/PageHeader";
import { Surface } from "../components/Surface";
import { useBlogs } from "../lib/hooks";

export function BlogsPage() {
  const blogs = useBlogs();
  const hasRows = (blogs.data?.length ?? 0) > 0;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Catalog"
        title="Blog URL 概览"
        description="查看目前已经记录到的所有 blog URL 以及它们的当前处理状态。"
      />
      <Surface title="Blog 列表" note="来自 /api/blogs">
        {blogs.isLoading ? <p>正在加载 blog 列表…</p> : null}
        {blogs.error ? <p className="error-copy">加载失败：{blogs.error.message}</p> : null}
        {!blogs.isLoading && !blogs.error && !hasRows ? <p>当前还没有记录到 blog。</p> : null}
        {hasRows ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Domain</th>
                  <th>URL</th>
                  <th>Status</th>
                  <th>Depth</th>
                  <th>Edges</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {blogs.data?.map((blog) => (
                  <tr key={blog.id}>
                    <td>{blog.id}</td>
                    <td>{blog.domain}</td>
                    <td className="url-cell">{blog.url}</td>
                    <td>
                      <span className={`status-chip status-${blog.crawl_status.toLowerCase()}`}>
                        {blog.crawl_status}
                      </span>
                    </td>
                    <td>{blog.depth}</td>
                    <td>{blog.friend_links_count}</td>
                    <td>{new Date(blog.updated_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Surface>
    </div>
  );
}
