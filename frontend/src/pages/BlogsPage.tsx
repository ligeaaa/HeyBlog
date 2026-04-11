import { FormEvent, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import { SiteIdentity } from "../components/SiteIdentity";
import { Surface } from "../components/Surface";
import {
  BLOG_CRAWL_STATUS_OPTIONS,
  useBlogCatalog,
  useBlogLookup,
  useCreateIngestionRequest,
  useIngestionRequestStatus,
  usePriorityIngestionRequests,
  useSearch,
} from "../lib/hooks";

const DEFAULT_PAGE_SIZE = 50;
const DEFAULT_QUEUE_SORT = "id_asc";
const DEFAULT_QUEUE_STATUSES = ["WAITING", "PROCESSING"] as const;
const DEFAULT_RELATION_LIMIT = 10;

type Props = {
  routeMode?: "canonical" | "search-alias";
};

function normalizePage(value: string | null) {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

function normalizeQueueSort(value: string | null) {
  const normalized = value?.trim() ?? "";
  return ["id_asc", "id_desc", "recent_activity", "connections", "recently_discovered"].includes(normalized)
    ? normalized
    : DEFAULT_QUEUE_SORT;
}

function normalizeQueueStatuses(value: string | null) {
  const allowed = new Set<string>(BLOG_CRAWL_STATUS_OPTIONS);
  const normalized = (value ?? "")
    .split(",")
    .map((item) => item.trim().toUpperCase())
    .filter((item, index, all) => item && allowed.has(item) && all.indexOf(item) === index);
  return normalized.length ? normalized : [...DEFAULT_QUEUE_STATUSES];
}

function normalizeRelationLimit(value: string | null) {
  const parsed = Number.parseInt(value ?? String(DEFAULT_RELATION_LIMIT), 10) || DEFAULT_RELATION_LIMIT;
  return Math.max(1, Math.min(parsed, 50));
}

function sameStatuses(left: string[], right: string[]) {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function usesDefaultQueueState(statuses: string[], sort: string) {
  return sameStatuses(statuses, [...DEFAULT_QUEUE_STATUSES]) && sort === DEFAULT_QUEUE_SORT;
}

function buildDiscoverySearchParams(options: {
  page: number;
  statuses: string[];
  sort: string;
  lookup: string;
  relationQuery: string;
  relationLimit: number;
}) {
  const next = new URLSearchParams();
  if (options.page > 1) {
    next.set("page", String(options.page));
  }
  if (!usesDefaultQueueState(options.statuses, options.sort)) {
    next.set("statuses", options.statuses.join(","));
    next.set("sort", options.sort);
  }
  if (options.lookup) {
    next.set("lookup", options.lookup);
  }
  if (options.relationQuery) {
    next.set("q", options.relationQuery);
    next.set("kind", "relations");
    if (options.relationLimit !== DEFAULT_RELATION_LIMIT) {
      next.set("limit", String(options.relationLimit));
    }
  }
  return next;
}

function formatDate(value: string | null) {
  if (!value) {
    return "暂无";
  }
  return new Date(value).toLocaleString();
}

function getQueueStatusHint(status: string) {
  if (status === "PROCESSING") {
    return "正在抓取，信息可能继续刷新。";
  }
  return "等待领取，进入队列后会按顺序抓取。";
}

function isTerminalIngestionStatus(status: string | null | undefined) {
  return status === "COMPLETED" || status === "FAILED" || status === "DEDUPED_EXISTING";
}

export function BlogsPage({ routeMode = "canonical" }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const committedPage = normalizePage(searchParams.get("page"));
  const committedStatuses = normalizeQueueStatuses(searchParams.get("statuses"));
  const committedSort = normalizeQueueSort(searchParams.get("sort"));
  const relationQuery = searchParams.get("kind") === "relations" ? searchParams.get("q")?.trim() ?? "" : "";
  const relationLimit = normalizeRelationLimit(searchParams.get("limit"));
  const committedLookup =
    searchParams.get("lookup")?.trim() ??
    (routeMode === "search-alias" && searchParams.get("kind") !== "relations"
      ? searchParams.get("q")?.trim() ?? ""
      : "");

  const [lookupInput, setLookupInput] = useState(committedLookup);
  const [relationInput, setRelationInput] = useState(relationQuery);
  const [relationLimitInput, setRelationLimitInput] = useState(String(relationLimit));
  const [email, setEmail] = useState("");
  const [activeRequest, setActiveRequest] = useState<{ requestId: number; requestToken: string } | null>(null);
  const [showRelationPanel, setShowRelationPanel] = useState(relationQuery.length > 0);

  const queueCatalog = useBlogCatalog({
    page: committedPage,
    pageSize: DEFAULT_PAGE_SIZE,
    statuses: committedStatuses,
    sort: committedSort,
  });
  const priorityRequests = usePriorityIngestionRequests();
  const lookup = useBlogLookup(committedLookup, { enabled: committedLookup.length > 0 });
  const relationSearch = useSearch(relationQuery, {
    enabled: relationQuery.length > 0,
    kind: "relations",
    limit: relationLimit,
  });
  const createIngestionRequest = useCreateIngestionRequest();
  const ingestionRequest = useIngestionRequestStatus(activeRequest?.requestId ?? null, activeRequest?.requestToken ?? null, {
    enabled: activeRequest != null,
    refetchInterval: activeRequest == null ? false : 2500,
  });

  useEffect(() => {
    setLookupInput(committedLookup);
    setRelationInput(relationQuery);
    setRelationLimitInput(String(relationLimit));
    if (relationQuery) {
      setShowRelationPanel(true);
    }
  }, [committedLookup, relationLimit, relationQuery]);

  useEffect(() => {
    if (!queueCatalog.data || queueCatalog.data.page === committedPage) {
      return;
    }
    setSearchParams(
      buildDiscoverySearchParams({
        page: queueCatalog.data.page,
        statuses: committedStatuses,
        sort: committedSort,
        lookup: committedLookup,
        relationQuery,
        relationLimit,
      }),
      { replace: true },
    );
  }, [
    committedLookup,
    committedPage,
    committedSort,
    committedStatuses,
    queueCatalog.data,
    relationLimit,
    relationQuery,
    setSearchParams,
  ]);

  const queueCurrentPage = queueCatalog.data?.page ?? committedPage;
  const queueTotalPages = queueCatalog.data?.total_pages ?? 0;
  const queueTotalItems = queueCatalog.data?.total_items ?? 0;
  const queueItems = queueCatalog.data?.items ?? [];
  const queuePageSize = queueCatalog.data?.page_size ?? DEFAULT_PAGE_SIZE;
  const pageStart = queueTotalItems === 0 ? 0 : (queueCurrentPage - 1) * queuePageSize + 1;
  const pageEnd = queueTotalItems === 0 ? 0 : pageStart + queueItems.length - 1;
  const createdRequest = createIngestionRequest.data;
  const activeRequestStatus = ingestionRequest.data;
  const createdActiveRequest =
    createdRequest && "request_id" in createdRequest && createdRequest.request_id != null ? createdRequest : null;
  const visibleIngestionStatus = activeRequestStatus ?? createdActiveRequest;
  const dedupedBlog = createdRequest && createdRequest.status === "DEDUPED_EXISTING" ? createdRequest.blog : null;

  const updateRoute = (overrides: Partial<{
    page: number;
    statuses: string[];
    sort: string;
    lookup: string;
    relationQuery: string;
    relationLimit: number;
  }>) => {
    setSearchParams(
      buildDiscoverySearchParams({
        page: overrides.page ?? committedPage,
        statuses: overrides.statuses ?? committedStatuses,
        sort: overrides.sort ?? committedSort,
        lookup: overrides.lookup ?? committedLookup,
        relationQuery: overrides.relationQuery ?? relationQuery,
        relationLimit: overrides.relationLimit ?? relationLimit,
      }),
    );
  };

  const changeQueuePage = (nextPage: number) => {
    const boundedPage = Math.max(1, queueTotalPages > 0 ? Math.min(nextPage, queueTotalPages) : nextPage);
    updateRoute({ page: boundedPage });
  };

  const handleLookupSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    updateRoute({ page: 1, lookup: lookupInput.trim() });
  };

  const clearLookup = () => {
    setLookupInput("");
    setEmail("");
    setActiveRequest(null);
    updateRoute({ page: 1, lookup: "" });
  };

  const handleRelationSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextQuery = relationInput.trim();
    if (!nextQuery) {
      updateRoute({ relationQuery: "", relationLimit: DEFAULT_RELATION_LIMIT });
      return;
    }
    updateRoute({
      relationQuery: nextQuery,
      relationLimit: normalizeRelationLimit(relationLimitInput),
    });
    setShowRelationPanel(true);
  };

  const clearRelationSearch = () => {
    setRelationInput("");
    setRelationLimitInput(String(DEFAULT_RELATION_LIMIT));
    updateRoute({ relationQuery: "", relationLimit: DEFAULT_RELATION_LIMIT });
  };

  const handleIngestionSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const response = await createIngestionRequest.mutateAsync({
      homepageUrl: committedLookup,
      email: email.trim(),
    });
    if (response.request_id != null && response.request_token != null) {
      setActiveRequest({
        requestId: response.request_id,
        requestToken: response.request_token,
      });
      return;
    }
    setActiveRequest(null);
  };

  const lookupStateLabel =
    committedLookup.length === 0
      ? "等待查库"
      : lookup.isLoading
        ? "查库中"
        : lookup.data?.total_matches
          ? "已命中"
          : "未命中";

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Discover"
        title="发现博客"
        description="统一查看当前系统队列、用户优先录入清单、博客 URL 是否已收录，以及兼容旧 /search 的关系线索入口。"
      />

      {routeMode === "search-alias" ? (
        <Surface title="兼容入口" note="旧 /search 链接现在会落到同一统一页面。">
          <p className="meta-copy">
            当前仍保留 `/search` 兼容路由，但主入口已经收敛到 `/blogs`。非 relations 查询会按“博客是否已收录”查库语义处理。
          </p>
        </Surface>
      ) : null}

      <div className="stats-grid">
        <div className="stat-card">
          <span>当前博客状态</span>
          <strong>{queueTotalItems}</strong>
        </div>
        <div className="stat-card">
          <span>优先处理清单</span>
          <strong>{priorityRequests.data?.length ?? 0}</strong>
        </div>
        <div className="stat-card">
          <span>查库状态</span>
          <strong>{lookupStateLabel}</strong>
        </div>
      </div>

      <Surface title="当前博客状态" note={`来自 /api/blogs/catalog · ${committedStatuses.join(" + ")} · ${committedSort}`}>
        <p className="meta-copy">
          这里固定聚焦系统当前正在处理或等待处理的博客首页，默认按 `id ASC` 展示，便于直接观察系统队列。
        </p>

        {queueCatalog.isLoading ? <p>正在加载当前博客状态…</p> : null}
        {queueCatalog.error ? <p className="error-copy">加载失败：{queueCatalog.error.message}</p> : null}
        {queueCatalog.isFetching && !queueCatalog.isLoading ? <p className="meta-copy">正在刷新系统队列…</p> : null}

        {!queueCatalog.isLoading && !queueCatalog.error ? (
          <p className="meta-copy">
            共 {queueTotalItems} 条，当前第 {queueCurrentPage} / {queueTotalPages || 1} 页
            {queueTotalItems > 0 ? `，显示 ${pageStart}-${pageEnd} 条` : ""}
          </p>
        ) : null}

        {!queueCatalog.isLoading && !queueCatalog.error && queueItems.length === 0 ? (
          <p>当前没有处于 WAITING 或 PROCESSING 状态的博客。</p>
        ) : null}

        {queueItems.length > 0 ? (
          <div className="blog-card-grid">
            {queueItems.map((blog) => (
              <article key={blog.id} className="blog-card">
                <div className="blog-card-head">
                  <Link className="card-link" to={`/blogs/${blog.id}`}>
                    <SiteIdentity title={blog.title} domain={blog.domain} iconUrl={blog.icon_url} />
                  </Link>
                  <span className={`status-chip status-${blog.crawl_status.toLowerCase()}`}>{blog.crawl_status}</span>
                </div>
                <p className="page-copy">{blog.url}</p>
                <div className="blog-card-metrics">
                  <span>创建时间：{formatDate(blog.created_at)}</span>
                  <span>最近活跃：{formatDate(blog.activity_at)}</span>
                  <span>{getQueueStatusHint(blog.crawl_status)}</span>
                </div>
                <div className="blog-card-actions">
                  <Link className="button-link primary-button" to={`/blogs/${blog.id}`}>
                    查看详情
                  </Link>
                  <Link
                    className="button-link secondary-button"
                    to={`/blogs?q=${encodeURIComponent(blog.title || blog.domain)}&kind=relations&limit=${DEFAULT_RELATION_LIMIT}`}
                  >
                    搜索相关线索
                  </Link>
                </div>
              </article>
            ))}
          </div>
        ) : null}

        {!queueCatalog.isLoading && !queueCatalog.error ? (
          <div className="pagination-row">
            <div className="page-actions">
              <button
                className="secondary-button"
                disabled={!queueCatalog.data?.has_prev}
                onClick={() => changeQueuePage(queueCurrentPage - 1)}
                type="button"
              >
                上一页
              </button>
              <button
                className="secondary-button"
                disabled={!queueCatalog.data?.has_next}
                onClick={() => changeQueuePage(queueCurrentPage + 1)}
                type="button"
              >
                下一页
              </button>
              <button
                className="secondary-button"
                disabled={queueCatalog.isFetching}
                onClick={() => void queueCatalog.refetch()}
                type="button"
              >
                手动刷新
              </button>
            </div>
          </div>
        ) : null}
      </Surface>

      <Surface title="优先处理博客清单" note="来自 /api/ingestion-requests · active-first · 最多 20 条">
        <p className="meta-copy">
          这里展示最终用户自助提交后进入优先录入队列的请求状态，不暴露联系邮箱或 request token。
        </p>

        {priorityRequests.isLoading ? <p>正在加载优先处理清单…</p> : null}
        {priorityRequests.error ? <p className="error-copy">加载失败：{priorityRequests.error.message}</p> : null}

        {!priorityRequests.isLoading && !priorityRequests.error && (priorityRequests.data?.length ?? 0) === 0 ? (
          <p>当前还没有公开可见的优先处理请求。</p>
        ) : null}

        {priorityRequests.data?.length ? (
          <ul className="result-list">
            {priorityRequests.data.map((request) => (
              <li key={request.request_id} className="result-item">
                <p className="result-title">请求状态：{request.status}</p>
                <p className="page-copy">{request.requested_url}</p>
                <p className="meta-copy">
                  创建时间 {formatDate(request.created_at)}
                  {request.blog ? ` · 博客状态 ${request.blog.crawl_status}` : ""}
                </p>
                {request.blog_id ? (
                  <Link className="result-link" to={`/blogs/${request.blog_id}`}>
                    {isTerminalIngestionStatus(request.status) ? "查看博客详情" : "查看当前博客状态"}
                  </Link>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}
      </Surface>

      <Surface title="检查博客 URL 是否已收录" note="来自 /api/blogs/lookup · identity-first">
        <form className="search-form" onSubmit={handleLookupSubmit}>
          <label className="search-field">
            <span>博客首页 URL</span>
            <input
              aria-label="博客首页 URL"
              name="lookup"
              type="url"
              value={lookupInput}
              onChange={(event) => setLookupInput(event.target.value)}
              placeholder="https://your-blog.example/"
            />
          </label>
          <button className="primary-button" type="submit">
            检查是否已收录
          </button>
          <button className="secondary-button" type="button" onClick={clearLookup}>
            清空
          </button>
        </form>

        {!committedLookup ? <p className="meta-copy">输入博客首页 URL 后，会优先按 canonical homepage identity 判断是否已在库中。</p> : null}
        {lookup.isLoading ? <p>正在查找匹配博客…</p> : null}
        {lookup.error ? <p className="error-copy">查库失败：{lookup.error.message}</p> : null}

        {lookup.data?.total_matches ? (
          <div className="result-list">
            {lookup.data.items.map((blog) => (
              <article key={blog.id} className="result-item">
                <Link className="card-link" to={`/blogs/${blog.id}`}>
                  <SiteIdentity title={blog.title} domain={blog.domain} iconUrl={blog.icon_url} />
                </Link>
                <p className="page-copy">{blog.url}</p>
                <p className="meta-copy">
                  命中原因：{lookup.data?.match_reason ?? "unknown"} · 当前状态 {blog.crawl_status}
                </p>
              </article>
            ))}
          </div>
        ) : null}

        {committedLookup && !lookup.isLoading && !lookup.error && lookup.data?.total_matches === 0 ? (
          <>
            <p className="meta-copy">当前没有命中现有博客记录。你可以沿用既有 priority ingestion 流程提交博客 URL 与联系方式。</p>
            <form className="search-form" onSubmit={handleIngestionSubmit}>
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
          </>
        ) : null}

        {createIngestionRequest.error ? <p className="error-copy">提交失败：{createIngestionRequest.error.message}</p> : null}

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
              {visibleIngestionStatus.blog ? (
                <p className="meta-copy">当前博客状态：{visibleIngestionStatus.blog.crawl_status}</p>
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

      <Surface title="高级关系线索搜索（兼容）" note="保留旧 /search?...kind=relations 的兼容入口">
        <div className="catalog-checkbox-row">
          <button
            className="secondary-button"
            onClick={() => setShowRelationPanel((current) => !current)}
            type="button"
          >
            {showRelationPanel ? "收起关系线索搜索" : "展开关系线索搜索"}
          </button>
          {relationQuery ? (
            <button className="secondary-button" onClick={clearRelationSearch} type="button">
              清空关系线索
            </button>
          ) : null}
        </div>

        {showRelationPanel ? (
          <>
            <form className="search-form" onSubmit={handleRelationSubmit}>
              <label className="search-field">
                <span>关系关键词</span>
                <input
                  aria-label="关系关键词"
                  name="q"
                  type="search"
                  value={relationInput}
                  onChange={(event) => setRelationInput(event.target.value)}
                  placeholder="例如 blogroll、friends、友情链接"
                />
              </label>
              <label className="search-field">
                <span>返回上限</span>
                <input
                  aria-label="每类上限"
                  inputMode="numeric"
                  min={1}
                  max={50}
                  type="number"
                  value={relationLimitInput}
                  onChange={(event) => setRelationLimitInput(event.target.value)}
                />
              </label>
              <button className="primary-button" type="submit">
                搜索关系线索
              </button>
            </form>

            {!relationQuery ? <p className="meta-copy">这里是旧 `/search?...kind=relations` 的兼容区，只在你需要关系线索时展开使用。</p> : null}
            {relationSearch.isLoading ? <p>正在搜索关系线索…</p> : null}
            {relationSearch.error ? <p className="error-copy">搜索失败：{relationSearch.error.message}</p> : null}

            {relationQuery && !relationSearch.isLoading && !relationSearch.error && relationSearch.data?.edges.length === 0 ? (
              <p>没有匹配的关系线索。</p>
            ) : null}

            {relationSearch.data?.edges.length ? (
              <ul className="result-list">
                {relationSearch.data.edges.map((edge) => (
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
            ) : null}
          </>
        ) : null}
      </Surface>
    </div>
  );
}
