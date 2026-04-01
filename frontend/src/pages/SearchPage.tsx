import { FormEvent, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import { Surface } from "../components/Surface";
import { useSearch } from "../lib/hooks";

function formatResultLabel(count: number, singular: string) {
  return `${count} ${singular}`;
}

export function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const committedQuery = searchParams.get("q")?.trim() ?? "";
  const [draftQuery, setDraftQuery] = useState(committedQuery);
  const search = useSearch(committedQuery, committedQuery.length > 0);

  useEffect(() => {
    setDraftQuery(committedQuery);
  }, [committedQuery]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextQuery = draftQuery.trim();
    setSearchParams(nextQuery ? { q: nextQuery } : {});
  };

  const hasResults =
    (search.data?.blogs.length ?? 0) > 0 ||
    (search.data?.edges.length ?? 0) > 0 ||
    (search.data?.logs.length ?? 0) > 0;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Discover"
        title="搜索发现"
        description="按关键词查找博客、友链线索与抓取日志，并从结果继续进入博客详情页。"
        actions={
          <form className="search-form" onSubmit={handleSubmit}>
            <label className="search-field">
              <span>关键词</span>
              <input
                name="q"
                type="search"
                value={draftQuery}
                onChange={(event) => setDraftQuery(event.target.value)}
                placeholder="比如 friend、blogroll、域名关键词"
              />
            </label>
            <button className="primary-button" type="submit">
              搜索
            </button>
          </form>
        }
      />

      {!committedQuery ? (
        <Surface title="开始探索" note="首版采用显式提交搜索">
          <p className="page-copy">
            输入关键词后点击“搜索”，系统会分别展示匹配到的博客、边和日志。博客结果是主区块，可直接跳详情继续探索。
          </p>
        </Surface>
      ) : null}

      {search.isLoading ? (
        <Surface title="搜索中" note={`q=${committedQuery}`}>
          <p>正在查找匹配结果…</p>
        </Surface>
      ) : null}

      {search.error ? (
        <Surface title="搜索失败" note={`q=${committedQuery}`}>
          <p className="error-copy">请求失败：{search.error.message}</p>
        </Surface>
      ) : null}

      {committedQuery && !search.isLoading && !search.error ? (
        <>
          <div className="stats-grid">
            <div className="stat-card">
              <span>博客结果</span>
              <strong>{formatResultLabel(search.data?.blogs.length ?? 0, "blogs")}</strong>
            </div>
            <div className="stat-card">
              <span>边线索</span>
              <strong>{formatResultLabel(search.data?.edges.length ?? 0, "edges")}</strong>
            </div>
            <div className="stat-card">
              <span>日志命中</span>
              <strong>{formatResultLabel(search.data?.logs.length ?? 0, "logs")}</strong>
            </div>
          </div>

          {!hasResults ? (
            <Surface title="没有匹配结果" note={`q=${committedQuery}`}>
              <p>当前没有找到匹配的博客、边或日志。可以尝试换一个域名、链接文本或抓取关键词。</p>
            </Surface>
          ) : null}

          <Surface title="博客结果" note="主区块，优先跳详情页">
            {search.data?.blogs.length ? (
              <ul className="result-list">
                {search.data.blogs.map((blog) => (
                  <li key={blog.id} className="result-item">
                    <Link className="result-link" to={`/blogs/${blog.id}`}>
                      {blog.domain}
                    </Link>
                    <p className="page-copy">{blog.url}</p>
                    <p className="meta-copy">ID {blog.id} · 状态 {blog.crawl_status}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p>没有匹配的博客结果。</p>
            )}
          </Surface>

          <Surface title="边线索" note="辅助区块">
            {search.data?.edges.length ? (
              <ul className="result-list">
                {search.data.edges.map((edge) => (
                  <li key={edge.id} className="result-item">
                    <p className="result-title">{edge.link_text || edge.link_url_raw}</p>
                    <p className="page-copy">{edge.link_url_raw}</p>
                    <p className="meta-copy">
                      {edge.from_blog_id} {"->"} {edge.to_blog_id}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p>没有匹配的边线索。</p>
            )}
          </Surface>

          <Surface title="日志命中" note="辅助区块">
            {search.data?.logs.length ? (
              <ul className="result-list">
                {search.data.logs.map((log) => (
                  <li key={log.id} className="result-item">
                    <p className="result-title">{log.message}</p>
                    <p className="meta-copy">
                      {log.stage} · {log.result} · blog_id {log.blog_id ?? "—"}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p>没有匹配的日志。</p>
            )}
          </Surface>
        </>
      ) : null}
    </div>
  );
}
