import { FormEvent, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import { SiteIdentity } from "../components/SiteIdentity";
import { Surface } from "../components/Surface";
import { useCreateIngestionRequest, useIngestionRequestStatus, useSearch } from "../lib/hooks";

type SearchKind = "all" | "blogs" | "relations";

function normalizeSearchKind(value: string | null): SearchKind {
  if (value === "blogs" || value === "relations") {
    return value;
  }
  return "all";
}

function normalizeSearchLimit(value: string | null) {
  const parsed = Number.parseInt(value ?? "10", 10) || 10;
  return Math.max(1, Math.min(parsed, 50));
}

function formatResultLabel(count: number, singular: string) {
  return `${count} ${singular}`;
}

function isTerminalIngestionStatus(status: string | null | undefined) {
  return status === "COMPLETED" || status === "FAILED" || status === "DEDUPED_EXISTING";
}

export function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const committedQuery = searchParams.get("q")?.trim() ?? "";
  const committedKind = normalizeSearchKind(searchParams.get("kind")?.trim() ?? null);
  const committedLimit = normalizeSearchLimit(searchParams.get("limit"));
  const [draftQuery, setDraftQuery] = useState(committedQuery);
  const [draftKind, setDraftKind] = useState<SearchKind>(committedKind);
  const [draftLimit, setDraftLimit] = useState(String(committedLimit));
  const [homepageUrl, setHomepageUrl] = useState("");
  const [email, setEmail] = useState("");
  const [activeRequest, setActiveRequest] = useState<{ requestId: number; requestToken: string } | null>(null);
  const search = useSearch(committedQuery, {
    enabled: committedQuery.length > 0,
    kind: committedKind,
    limit: committedLimit,
  });
  const createIngestionRequest = useCreateIngestionRequest();
  const ingestionRequest = useIngestionRequestStatus(activeRequest?.requestId ?? null, activeRequest?.requestToken ?? null, {
    enabled: activeRequest != null,
    refetchInterval: activeRequest == null ? false : 2500,
  });

  useEffect(() => {
    setDraftQuery(committedQuery);
    setDraftKind(committedKind);
    setDraftLimit(String(committedLimit));
  }, [committedKind, committedLimit, committedQuery]);

  useEffect(() => {
    if (committedQuery) {
      setHomepageUrl((current) => current || committedQuery);
    }
  }, [committedQuery]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextQuery = draftQuery.trim();
    if (!nextQuery) {
      setSearchParams({});
      return;
    }
    setSearchParams({
      q: nextQuery,
      kind: draftKind,
      limit: String(normalizeSearchLimit(draftLimit)),
    });
  };

  const handleIngestionSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const response = await createIngestionRequest.mutateAsync({
      homepageUrl: homepageUrl.trim(),
      email: email.trim(),
    });
    if (response.request_id != null && response.request_token != null) {
      setActiveRequest({
        requestId: response.request_id,
        requestToken: response.request_token,
      });
    } else {
      setActiveRequest(null);
    }
  };

  const hasResults = (search.data?.blogs.length ?? 0) > 0 || (search.data?.edges.length ?? 0) > 0;
  const createdRequest = createIngestionRequest.data;
  const activeRequestStatus = ingestionRequest.data;
  const visibleIngestionStatus =
    activeRequestStatus ?? (createdRequest && "id" in createdRequest ? createdRequest : null);
  const dedupedBlog = createdRequest && createdRequest.status === "DEDUPED_EXISTING" ? createdRequest.blog : null;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Discover"
        title="搜索发现"
        description="按站点名、标题、链接文本和关系线索做探索。这里仍是轻量搜索，但已经更像一个继续深入发现的入口。"
        actions={
          <form className="search-form" onSubmit={handleSubmit}>
            <label className="search-field">
              <span>关键词</span>
              <input
                aria-label="关键词"
                name="q"
                type="search"
                value={draftQuery}
                onChange={(event) => setDraftQuery(event.target.value)}
                placeholder="比如 blogroll、域名关键词、站点标题"
              />
            </label>
            <label className="search-field">
              <span>模式</span>
              <select
                aria-label="模式"
                value={draftKind}
                onChange={(event) => setDraftKind(normalizeSearchKind(event.target.value))}
              >
                <option value="all">全部</option>
                <option value="blogs">只看博客</option>
                <option value="relations">只看关系线索</option>
              </select>
            </label>
            <label className="search-field">
              <span>每类上限</span>
              <input
                aria-label="每类上限"
                inputMode="numeric"
                min={1}
                max={50}
                type="number"
                value={draftLimit}
                onChange={(event) => setDraftLimit(event.target.value)}
              />
            </label>
            <button className="primary-button" type="submit">
              搜索
            </button>
          </form>
        }
      />

      {!committedQuery ? (
        <Surface title="开始探索" note="首版使用显式提交搜索">
          <div className="result-list">
            <article className="result-item">
              <p className="result-title">试试站点名</p>
              <p className="meta-copy">例如 `alpha.example` 或博客标题关键词</p>
            </article>
            <article className="result-item">
              <p className="result-title">试试关系线索</p>
              <p className="meta-copy">例如 `blogroll`、`friends`、`友情链接`</p>
            </article>
          </div>
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
              <span>关系线索</span>
              <strong>{formatResultLabel(search.data?.edges.length ?? 0, "relations")}</strong>
            </div>
            <div className="stat-card">
              <span>当前模式</span>
              <strong>{search.data?.kind ?? committedKind}</strong>
            </div>
          </div>

          {!hasResults ? (
            <Surface title="没有匹配结果" note={`q=${committedQuery}`}>
              <p>当前没有找到匹配的博客或关系线索。可以尝试换一个域名、标题词、链接文本，或者切到“全部”模式继续找。</p>
              <form className="search-form" onSubmit={handleIngestionSubmit}>
                <label className="search-field">
                  <span>博客首页 URL</span>
                  <input
                    aria-label="博客首页 URL"
                    name="homepage_url"
                    type="url"
                    required
                    value={homepageUrl}
                    onChange={(event) => setHomepageUrl(event.target.value)}
                    placeholder="https://your-blog.example/"
                  />
                </label>
                <label className="search-field">
                  <span>联系邮箱</span>
                  <input
                    aria-label="联系邮箱"
                    name="email"
                    type="email"
                    required
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="you@example.com"
                  />
                </label>
                <button className="primary-button" type="submit" disabled={createIngestionRequest.isPending}>
                  {createIngestionRequest.isPending ? "提交中…" : "提交你的博客首页"}
                </button>
              </form>

              {createIngestionRequest.error ? (
                <p className="error-copy">提交失败：{createIngestionRequest.error.message}</p>
              ) : null}

              {dedupedBlog ? (
                <p className="meta-copy">
                  这个博客已经收录，<Link className="result-link" to={`/blogs/${dedupedBlog.id}`}>直接查看详情</Link>。
                </p>
              ) : null}

              {visibleIngestionStatus ? (
                <div className="result-list">
                  <article className="result-item">
                    <p className="result-title">优先录入请求状态：{visibleIngestionStatus.status}</p>
                    <p className="page-copy">{visibleIngestionStatus.requested_url}</p>
                    <p className="meta-copy">联系邮箱：{visibleIngestionStatus.email}</p>
                    {visibleIngestionStatus.blog ? (
                      <p className="meta-copy">
                        当前博客状态：{visibleIngestionStatus.blog.crawl_status}
                      </p>
                    ) : null}
                    {visibleIngestionStatus.blog_id ? (
                      <Link className="result-link" to={`/blogs/${visibleIngestionStatus.blog_id}`}>
                        {isTerminalIngestionStatus(visibleIngestionStatus.status) ? "查看博客详情" : "稍后查看博客详情"}
                      </Link>
                    ) : null}
                  </article>
                </div>
              ) : null}
            </Surface>
          ) : null}

          <Surface title="博客结果" note="主区块，优先直达详情页">
            {search.data?.blogs.length ? (
              <ul className="result-list">
                {search.data.blogs.map((blog) => (
                  <li key={blog.id} className="result-item">
                    <Link className="card-link" to={`/blogs/${blog.id}`}>
                      <SiteIdentity title={blog.title} domain={blog.domain} iconUrl={blog.icon_url} />
                    </Link>
                    <p className="page-copy">{blog.url}</p>
                    <p className="meta-copy">
                      状态 {blog.crawl_status} · 关系线索 {blog.connection_count}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p>没有匹配的博客结果。</p>
            )}
          </Surface>

          <Surface title="关系线索" note="帮助你从链接关系继续探索">
            {search.data?.edges.length ? (
              <ul className="result-list">
                {search.data.edges.map((edge) => (
                  <li key={edge.id} className="result-item">
                    <p className="result-title">{edge.link_text || edge.link_url_raw}</p>
                    <p className="page-copy">{edge.link_url_raw}</p>
                    <p className="meta-copy">
                      {edge.from_blog?.domain ?? edge.from_blog_id} {"->"} {edge.to_blog?.domain ?? edge.to_blog_id}
                    </p>
                    {edge.to_blog ? (
                      <Link className="result-link" to={`/blogs/${edge.to_blog.id}`}>
                        前往 {edge.to_blog.title?.trim() || edge.to_blog.domain}
                      </Link>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p>没有匹配的关系线索。</p>
            )}
          </Surface>
        </>
      ) : null}
    </div>
  );
}
