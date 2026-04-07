import { FormEvent, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import { SiteIdentity } from "../components/SiteIdentity";
import { Surface } from "../components/Surface";
import { BLOG_CRAWL_STATUS_OPTIONS, useBlogCatalog } from "../lib/hooks";

const DEFAULT_PAGE_SIZE = 50;
const FILTER_DEBOUNCE_MS = 300;

type CatalogFilters = {
  q: string;
  site: string;
  url: string;
  status: string;
  sort: string;
  hasTitle: boolean;
  hasIcon: boolean;
  minConnections: string;
};

function normalizePage(value: string | null) {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

function readFilter(searchParams: URLSearchParams, key: keyof Pick<CatalogFilters, "q" | "site" | "url" | "status" | "sort" | "minConnections">) {
  return searchParams.get(key)?.trim() ?? "";
}

function readBooleanFilter(searchParams: URLSearchParams, key: "hasTitle" | "hasIcon") {
  return searchParams.get(key) === "true";
}

function sameFilters(left: CatalogFilters, right: CatalogFilters) {
  return (
    left.q === right.q &&
    left.site === right.site &&
    left.url === right.url &&
    left.status === right.status &&
    left.sort === right.sort &&
    left.hasTitle === right.hasTitle &&
    left.hasIcon === right.hasIcon &&
    left.minConnections === right.minConnections
  );
}

function buildSearchParams(page: number, filters: CatalogFilters) {
  const next = new URLSearchParams();
  if (page > 1) {
    next.set("page", String(page));
  }
  if (filters.q) {
    next.set("q", filters.q);
  }
  if (filters.site) {
    next.set("site", filters.site);
  }
  if (filters.url) {
    next.set("url", filters.url);
  }
  if (filters.status) {
    next.set("status", filters.status);
  }
  if (filters.sort && filters.sort !== "id_desc") {
    next.set("sort", filters.sort);
  }
  if (filters.hasTitle) {
    next.set("hasTitle", "true");
  }
  if (filters.hasIcon) {
    next.set("hasIcon", "true");
  }
  if (filters.minConnections) {
    next.set("minConnections", filters.minConnections);
  }
  return next;
}

function formatRelativeActivity(value: string | null) {
  if (!value) {
    return "暂无活跃信号";
  }
  return new Date(value).toLocaleString();
}

function formatConnectionHint(connectionCount: number, friendLinksCount: number) {
  if (connectionCount > 0) {
    return `关系线索 ${connectionCount}`;
  }
  return `友链记录 ${friendLinksCount}`;
}

function getStatusHint(status: string) {
  switch (status) {
    case "FINISHED":
      return "已完成抓取，可优先查看";
    case "PROCESSING":
      return "正在抓取，信息可能继续更新";
    case "FAILED":
      return "抓取失败，资料可能不完整";
    default:
      return "等待抓取，先看已有基础资料";
  }
}

export function BlogsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const committedPage = normalizePage(searchParams.get("page"));
  const committedFilters = {
    q: readFilter(searchParams, "q"),
    site: readFilter(searchParams, "site"),
    url: readFilter(searchParams, "url"),
    status: readFilter(searchParams, "status"),
    sort: readFilter(searchParams, "sort") || "id_desc",
    hasTitle: readBooleanFilter(searchParams, "hasTitle"),
    hasIcon: readBooleanFilter(searchParams, "hasIcon"),
    minConnections: readFilter(searchParams, "minConnections"),
  };
  const [draftFilters, setDraftFilters] = useState<CatalogFilters>(committedFilters);
  const [pageInput, setPageInput] = useState(String(committedPage));
  const catalog = useBlogCatalog({
    page: committedPage,
    pageSize: DEFAULT_PAGE_SIZE,
    q: committedFilters.q || null,
    site: committedFilters.site || null,
    url: committedFilters.url || null,
    status: committedFilters.status || null,
    sort: committedFilters.sort,
    hasTitle: committedFilters.hasTitle ? true : null,
    hasIcon: committedFilters.hasIcon ? true : null,
    minConnections: committedFilters.minConnections
      ? Number.parseInt(committedFilters.minConnections, 10) || 0
      : null,
  });

  useEffect(() => {
    setDraftFilters(committedFilters);
    setPageInput(String(committedPage));
  }, [
    committedFilters.q,
    committedFilters.site,
    committedFilters.url,
    committedFilters.status,
    committedFilters.sort,
    committedFilters.hasTitle,
    committedFilters.hasIcon,
    committedFilters.minConnections,
    committedPage,
  ]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      if (sameFilters(draftFilters, committedFilters)) {
        return;
      }
      setSearchParams(buildSearchParams(1, draftFilters), { replace: true });
    }, FILTER_DEBOUNCE_MS);

    return () => window.clearTimeout(timeoutId);
  }, [committedFilters, draftFilters, setSearchParams]);

  useEffect(() => {
    if (!catalog.data || catalog.data.page === committedPage) {
      return;
    }
    setSearchParams(buildSearchParams(catalog.data.page, committedFilters), { replace: true });
  }, [catalog.data, committedFilters, committedPage, setSearchParams]);

  const hasRows = (catalog.data?.items.length ?? 0) > 0;
  const currentPage = catalog.data?.page ?? committedPage;
  const totalPages = catalog.data?.total_pages ?? 0;
  const totalItems = catalog.data?.total_items ?? 0;
  const pageSize = catalog.data?.page_size ?? DEFAULT_PAGE_SIZE;
  const pageStart = totalItems === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const pageEnd = totalItems === 0 ? 0 : pageStart + (catalog.data?.items.length ?? 0) - 1;

  const setFilter = <K extends keyof CatalogFilters>(key: K, value: CatalogFilters[K]) => {
    setDraftFilters((current) => ({ ...current, [key]: value }));
  };

  const changePage = (nextPage: number) => {
    const boundedPage = Math.max(1, totalPages > 0 ? Math.min(nextPage, totalPages) : nextPage);
    setSearchParams(buildSearchParams(boundedPage, committedFilters));
  };

  const handlePageSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    changePage(normalizePage(pageInput));
  };

  const clearFilters = () => {
    const nextFilters = {
      q: "",
      site: "",
      url: "",
      status: "",
      sort: "id_desc",
      hasTitle: false,
      hasIcon: false,
      minConnections: "",
    };
    setDraftFilters(nextFilters);
    setSearchParams(new URLSearchParams());
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Discover"
        title="发现博客"
        description="把当前抓到的博客整理成可浏览、可判断、可继续点进去的发现入口。先用身份、活跃度和关系线索帮你快速决定值不值得看。"
      />

      <div className="stats-grid">
        <div className="stat-card">
          <span>当前结果</span>
          <strong>{totalItems}</strong>
        </div>
        <div className="stat-card">
          <span>排序方式</span>
          <strong>{draftFilters.sort === "id_desc" ? "最近收录" : draftFilters.sort}</strong>
        </div>
        <div className="stat-card">
          <span>入口提示</span>
          <strong>{draftFilters.hasTitle || draftFilters.hasIcon ? "优先完整资料" : "先广泛探索"}</strong>
        </div>
      </div>

      <Surface title="发现控制台" note={`来自 /api/blogs/catalog · 每页 ${DEFAULT_PAGE_SIZE} 条`}>
        <div className="catalog-controls">
          <div className="catalog-summary">
            <p className="meta-copy">
              用站点身份、抓取状态和关系密度快速缩小范围；筛选仍由 URL 参数驱动，可直接分享当前视图。
            </p>
          </div>
          <div className="search-form">
            <label className="search-field">
              <span>通用搜索</span>
              <input
                aria-label="通用搜索"
                name="q"
                type="search"
                value={draftFilters.q}
                onChange={(event) => setFilter("q", event.target.value)}
                placeholder="匹配标题、域名或 URL"
              />
            </label>
            <label className="search-field">
              <span>站点</span>
              <input
                aria-label="站点"
                name="site"
                type="search"
                value={draftFilters.site}
                onChange={(event) => setFilter("site", event.target.value)}
                placeholder="匹配 title / domain"
              />
            </label>
            <label className="search-field">
              <span>URL</span>
              <input
                aria-label="URL"
                name="url"
                type="search"
                value={draftFilters.url}
                onChange={(event) => setFilter("url", event.target.value)}
                placeholder="匹配 url / normalized_url"
              />
            </label>
            <label className="search-field">
              <span>状态</span>
              <select
                aria-label="状态"
                name="status"
                value={draftFilters.status}
                onChange={(event) => setFilter("status", event.target.value)}
              >
                <option value="">全部状态</option>
                {BLOG_CRAWL_STATUS_OPTIONS.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
            </label>
            <label className="search-field">
              <span>排序</span>
              <select
                aria-label="排序"
                name="sort"
                value={draftFilters.sort}
                onChange={(event) => setFilter("sort", event.target.value)}
              >
                <option value="id_desc">最近收录</option>
                <option value="recent_activity">最近活跃</option>
                <option value="connections">连接更丰富</option>
                <option value="recently_discovered">最近发现</option>
              </select>
            </label>
            <label className="search-field">
              <span>最少关系线索</span>
              <input
                aria-label="最少关系线索"
                inputMode="numeric"
                min={0}
                name="minConnections"
                type="number"
                value={draftFilters.minConnections}
                onChange={(event) => setFilter("minConnections", event.target.value)}
                placeholder="0"
              />
            </label>
          </div>
          <div className="catalog-checkbox-row">
            <label className="toggle-pill">
              <input
                aria-label="仅显示有标题"
                checked={draftFilters.hasTitle}
                type="checkbox"
                onChange={(event) => setFilter("hasTitle", event.target.checked)}
              />
              <span>仅显示有标题</span>
            </label>
            <label className="toggle-pill">
              <input
                aria-label="仅显示有图标"
                checked={draftFilters.hasIcon}
                type="checkbox"
                onChange={(event) => setFilter("hasIcon", event.target.checked)}
              />
              <span>仅显示有图标</span>
            </label>
            <button
              className="secondary-button"
              disabled={catalog.isFetching}
              onClick={() => void catalog.refetch()}
              type="button"
            >
              手动刷新
            </button>
            <button className="secondary-button" onClick={clearFilters} type="button">
              清空筛选
            </button>
          </div>
        </div>

        {catalog.isLoading ? <p>正在加载当前页…</p> : null}
        {catalog.error ? <p className="error-copy">加载失败：{catalog.error.message}</p> : null}
        {catalog.isFetching && !catalog.isLoading ? (
          <p className="meta-copy">正在更新当前页结果…</p>
        ) : null}

        {!catalog.isLoading && !catalog.error ? (
          <div className="catalog-summary">
            <p className="meta-copy">
              共 {totalItems} 条，当前第 {currentPage} / {totalPages || 1} 页
              {totalItems > 0 ? `，显示 ${pageStart}-${pageEnd} 条` : ""}
            </p>
          </div>
        ) : null}

        {!catalog.isLoading && !catalog.error && !hasRows ? <p>当前筛选下没有匹配的 blog。</p> : null}

        {hasRows ? (
          <div className="blog-card-grid">
            {catalog.data?.items.map((blog) => (
              <article key={blog.id} className="blog-card">
                <div className="blog-card-head">
                  <Link className="card-link" to={`/blogs/${blog.id}`}>
                    <SiteIdentity title={blog.title} domain={blog.domain} iconUrl={blog.icon_url} />
                  </Link>
                  <span className={`status-chip status-${blog.crawl_status.toLowerCase()}`}>
                    {blog.crawl_status}
                  </span>
                </div>
                <p className="page-copy">{blog.url}</p>
                <div className="blog-card-metrics">
                  <span>活跃信号：{formatRelativeActivity(blog.activity_at)}</span>
                  <span>{formatConnectionHint(blog.connection_count, blog.friend_links_count)}</span>
                  <span>{getStatusHint(blog.crawl_status)}</span>
                </div>
                <div className="blog-card-actions">
                  <Link className="button-link primary-button" to={`/blogs/${blog.id}`}>
                    查看详情
                  </Link>
                  <Link
                    className="button-link secondary-button"
                    to={`/search?q=${encodeURIComponent(blog.title || blog.domain)}`}
                  >
                    搜索相关线索
                  </Link>
                </div>
              </article>
            ))}
          </div>
        ) : null}

        {!catalog.isLoading && !catalog.error ? (
          <div className="pagination-row">
            <div className="page-actions">
              <button
                className="secondary-button"
                disabled={!catalog.data?.has_prev}
                onClick={() => changePage(currentPage - 1)}
                type="button"
              >
                上一页
              </button>
              <button
                className="secondary-button"
                disabled={!catalog.data?.has_next}
                onClick={() => changePage(currentPage + 1)}
                type="button"
              >
                下一页
              </button>
            </div>
            <form className="page-jump-form" onSubmit={handlePageSubmit}>
              <label className="search-field">
                <span>跳转页码</span>
                <input
                  aria-label="跳转页码"
                  inputMode="numeric"
                  min={1}
                  name="page"
                  onChange={(event) => setPageInput(event.target.value)}
                  type="number"
                  value={pageInput}
                />
              </label>
              <button className="primary-button" type="submit">
                跳转
              </button>
            </form>
          </div>
        ) : null}
      </Surface>
    </div>
  );
}
