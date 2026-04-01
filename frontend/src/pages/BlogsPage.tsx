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
};

function normalizePage(value: string | null) {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

function readFilter(searchParams: URLSearchParams, key: keyof CatalogFilters) {
  return searchParams.get(key)?.trim() ?? "";
}

function sameFilters(left: CatalogFilters, right: CatalogFilters) {
  return (
    left.q === right.q &&
    left.site === right.site &&
    left.url === right.url &&
    left.status === right.status
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
  return next;
}

export function BlogsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const committedPage = normalizePage(searchParams.get("page"));
  const committedFilters = {
    q: readFilter(searchParams, "q"),
    site: readFilter(searchParams, "site"),
    url: readFilter(searchParams, "url"),
    status: readFilter(searchParams, "status"),
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
  });

  useEffect(() => {
    setDraftFilters(committedFilters);
    setPageInput(String(committedPage));
  }, [
    committedFilters.q,
    committedFilters.site,
    committedFilters.status,
    committedFilters.url,
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
  }, [
    committedFilters.q,
    committedFilters.site,
    committedFilters.status,
    committedFilters.url,
    draftFilters.q,
    draftFilters.site,
    draftFilters.status,
    draftFilters.url,
    setSearchParams,
  ]);

  useEffect(() => {
    if (!catalog.data || catalog.data.page === committedPage) {
      return;
    }
    setSearchParams(buildSearchParams(catalog.data.page, committedFilters), { replace: true });
  }, [
    catalog.data,
    committedFilters.q,
    committedFilters.site,
    committedFilters.status,
    committedFilters.url,
    committedPage,
    setSearchParams,
  ]);

  const hasRows = (catalog.data?.items.length ?? 0) > 0;
  const currentPage = catalog.data?.page ?? committedPage;
  const totalPages = catalog.data?.total_pages ?? 0;
  const totalItems = catalog.data?.total_items ?? 0;
  const pageSize = catalog.data?.page_size ?? DEFAULT_PAGE_SIZE;
  const pageStart = totalItems === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const pageEnd = totalItems === 0 ? 0 : pageStart + (catalog.data?.items.length ?? 0) - 1;

  const setFilter = (key: keyof CatalogFilters, value: string) => {
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
    setDraftFilters({ q: "", site: "", url: "", status: "" });
    setSearchParams(new URLSearchParams());
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Catalog"
        title="Blog URL 概览"
        description="按页查看已记录的 blog，并按关键词、站点、URL 和状态筛选。概览页只加载当前页，避免全量渲染。"
      />
      <Surface title="Blog 列表" note={`来自 /api/blogs/catalog · 每页 ${DEFAULT_PAGE_SIZE} 条`}>
        <div className="catalog-controls">
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
              <span>Status</span>
              <select
                aria-label="Status"
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
          </div>
          <div className="page-actions">
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
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>站点</th>
                  <th>URL</th>
                  <th>Status</th>
                  <th>Edges</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {catalog.data?.items.map((blog) => (
                  <tr key={blog.id}>
                    <td>
                      <Link className="table-link" to={`/blogs/${blog.id}`}>
                        {blog.id}
                      </Link>
                    </td>
                    <td>
                      <Link className="table-link" to={`/blogs/${blog.id}`}>
                        <SiteIdentity
                          compact
                          title={blog.title}
                          domain={blog.domain}
                          iconUrl={blog.icon_url}
                        />
                      </Link>
                    </td>
                    <td className="url-cell">{blog.url}</td>
                    <td>
                      <span className={`status-chip status-${blog.crawl_status.toLowerCase()}`}>
                        {blog.crawl_status}
                      </span>
                    </td>
                    <td>{blog.friend_links_count}</td>
                    <td>{new Date(blog.updated_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
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
