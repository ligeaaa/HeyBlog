import { FormEvent, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import { SiteIdentity } from "../components/SiteIdentity";
import { Surface } from "../components/Surface";
import { BlogLabelTagRecord, BlogLabelingCandidateRecord } from "../lib/api";
import {
  useBlogLabelingCandidates,
  useCreateBlogLabelTag,
  useReplaceBlogLinkLabels,
} from "../lib/hooks";

const DEFAULT_PAGE_SIZE = 50;
const FILTER_DEBOUNCE_MS = 300;

type LabelingFilters = {
  q: string;
  label: string;
  labeled: "" | "true" | "false";
  sort: string;
};

function normalizePage(value: string | null) {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

function readFilter(searchParams: URLSearchParams, key: keyof LabelingFilters) {
  return searchParams.get(key)?.trim() ?? "";
}

function sameFilters(left: LabelingFilters, right: LabelingFilters) {
  return (
    left.q === right.q &&
    left.label === right.label &&
    left.labeled === right.labeled &&
    left.sort === right.sort
  );
}

function buildSearchParams(page: number, filters: LabelingFilters) {
  const next = new URLSearchParams();
  if (page > 1) {
    next.set("page", String(page));
  }
  if (filters.q) {
    next.set("q", filters.q);
  }
  if (filters.label) {
    next.set("label", filters.label);
  }
  if (filters.labeled) {
    next.set("labeled", filters.labeled);
  }
  if (filters.sort && filters.sort !== "id_desc") {
    next.set("sort", filters.sort);
  }
  return next;
}

function labelsSummary(blog: BlogLabelingCandidateRecord) {
  if (!blog.labels.length) {
    return "未标注";
  }
  return blog.labels.map((label) => label.name).join(" / ");
}

function labeledHint(blog: BlogLabelingCandidateRecord) {
  if (!blog.is_labeled || !blog.last_labeled_at) {
    return "还没有人工标签";
  }
  return `最近标注：${new Date(blog.last_labeled_at).toLocaleString()}`;
}

function nextTagIds(
  blog: BlogLabelingCandidateRecord,
  tag: BlogLabelTagRecord,
) {
  const current = new Set(blog.labels.map((label) => label.id));
  if (current.has(tag.id)) {
    current.delete(tag.id);
  } else {
    current.add(tag.id);
  }
  return Array.from(current).sort((left, right) => left - right);
}

export function BlogLabelingPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const committedPage = normalizePage(searchParams.get("page"));
  const committedFilters: LabelingFilters = {
    q: readFilter(searchParams, "q"),
    label: readFilter(searchParams, "label"),
    labeled: (readFilter(searchParams, "labeled") as LabelingFilters["labeled"]) || "",
    sort: readFilter(searchParams, "sort") || "id_desc",
  };
  const [draftFilters, setDraftFilters] = useState<LabelingFilters>(committedFilters);
  const [pageInput, setPageInput] = useState(String(committedPage));
  const [newTagName, setNewTagName] = useState("");
  const candidates = useBlogLabelingCandidates({
    page: committedPage,
    pageSize: DEFAULT_PAGE_SIZE,
    q: committedFilters.q || null,
    label: committedFilters.label || null,
    labeled:
      committedFilters.labeled === "true"
        ? true
        : committedFilters.labeled === "false"
          ? false
          : null,
    sort: committedFilters.sort,
  });
  const replaceLabels = useReplaceBlogLinkLabels();
  const createTag = useCreateBlogLabelTag();

  useEffect(() => {
    setDraftFilters(committedFilters);
    setPageInput(String(committedPage));
  }, [committedFilters.q, committedFilters.label, committedFilters.labeled, committedFilters.sort, committedPage]);

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
    if (!candidates.data || candidates.data.page === committedPage) {
      return;
    }
    setSearchParams(buildSearchParams(candidates.data.page, committedFilters), { replace: true });
  }, [candidates.data, committedFilters, committedPage, setSearchParams]);

  const currentPage = candidates.data?.page ?? committedPage;
  const totalPages = candidates.data?.total_pages ?? 0;
  const totalItems = candidates.data?.total_items ?? 0;
  const pageSize = candidates.data?.page_size ?? DEFAULT_PAGE_SIZE;
  const hasRows = (candidates.data?.items.length ?? 0) > 0;
  const pageStart = totalItems === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const pageEnd = totalItems === 0 ? 0 : pageStart + (candidates.data?.items.length ?? 0) - 1;

  const setFilter = <K extends keyof LabelingFilters>(key: K, value: LabelingFilters[K]) => {
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

  const handleCreateTag = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalized = newTagName.trim();
    if (!normalized) {
      return;
    }
    await createTag.mutateAsync({ name: normalized });
    setNewTagName("");
  };

  const clearFilters = () => {
    const nextFilters: LabelingFilters = {
      q: "",
      label: "",
      labeled: "",
      sort: "id_desc",
    };
    setDraftFilters(nextFilters);
    setSearchParams(new URLSearchParams());
  };

  const availableTags = candidates.data?.available_tags ?? [];

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Labeling"
        title="博客人工标注台"
        description="支持多标签标注。你可以给一个站点同时打上 blog、unknown、official、government 等多个标签，并直接在前端新建标签类型。"
      />

      <div className="stats-grid">
        <div className="stat-card">
          <span>候选总数</span>
          <strong>{totalItems}</strong>
        </div>
        <div className="stat-card">
          <span>标签类型</span>
          <strong>{availableTags.length}</strong>
        </div>
        <div className="stat-card">
          <span>当前筛选</span>
          <strong>{draftFilters.labeled === "false" ? "仅未标注" : draftFilters.label || "全部"}</strong>
        </div>
      </div>

      <Surface title="标签类型" note="先维护标签字典，再给具体站点分配多个标签。">
        <form className="search-form" onSubmit={handleCreateTag}>
          <label className="search-field">
            <span>新标签名</span>
            <input
              aria-label="新标签名"
              type="text"
              value={newTagName}
              onChange={(event) => setNewTagName(event.target.value)}
              placeholder="例如 official、government、unknown"
            />
          </label>
          <button className="primary-button" disabled={createTag.isPending} type="submit">
            新建标签
          </button>
        </form>
        {createTag.error ? <p className="error-copy">新建失败：{createTag.error.message}</p> : null}
        <div className="catalog-checkbox-row">
          {availableTags.map((tag) => (
            <span key={tag.id} className="toggle-pill">
              {tag.name}
            </span>
          ))}
        </div>
      </Surface>

      <Surface title="标注控制台" note={`来自 /api/admin/blog-labeling/candidates · 每页 ${DEFAULT_PAGE_SIZE} 条`}>
        <div className="catalog-controls">
          <div className="search-form">
            <label className="search-field">
              <span>通用搜索</span>
              <input
                aria-label="通用搜索"
                type="search"
                value={draftFilters.q}
                onChange={(event) => setFilter("q", event.target.value)}
                placeholder="匹配标题、域名或 URL"
              />
            </label>
            <label className="search-field">
              <span>标签筛选</span>
              <select
                aria-label="标签筛选"
                value={draftFilters.label}
                onChange={(event) => setFilter("label", event.target.value)}
              >
                <option value="">全部标签</option>
                {availableTags.map((tag) => (
                  <option key={tag.id} value={tag.slug}>
                    {tag.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="search-field">
              <span>标注状态</span>
              <select
                aria-label="标注状态"
                value={draftFilters.labeled}
                onChange={(event) => setFilter("labeled", event.target.value as LabelingFilters["labeled"])}
              >
                <option value="">全部</option>
                <option value="false">仅未标注</option>
                <option value="true">仅已标注</option>
              </select>
            </label>
            <label className="search-field">
              <span>排序</span>
              <select
                aria-label="排序"
                value={draftFilters.sort}
                onChange={(event) => setFilter("sort", event.target.value)}
              >
                <option value="id_desc">最近收录</option>
                <option value="recent_activity">最近活跃</option>
                <option value="recently_labeled">最近标注</option>
              </select>
            </label>
          </div>
          <div className="catalog-checkbox-row">
            <button
              className="secondary-button"
              disabled={candidates.isFetching}
              onClick={() => void candidates.refetch()}
              type="button"
            >
              手动刷新
            </button>
            <button className="secondary-button" onClick={clearFilters} type="button">
              清空筛选
            </button>
          </div>
        </div>

        {candidates.isLoading ? <p>正在加载待标注候选…</p> : null}
        {candidates.error ? <p className="error-copy">加载失败：{candidates.error.message}</p> : null}
        {replaceLabels.error ? <p className="error-copy">写入失败：{replaceLabels.error.message}</p> : null}
        {!candidates.isLoading && !candidates.error ? (
          <div className="catalog-summary">
            <p className="meta-copy">
              共 {totalItems} 条，当前第 {currentPage} / {totalPages || 1} 页
              {totalItems > 0 ? `，显示 ${pageStart}-${pageEnd} 条` : ""}
            </p>
          </div>
        ) : null}

        {!candidates.isLoading && !candidates.error && !hasRows ? <p>当前筛选下没有待标注 blog。</p> : null}

        {hasRows ? (
          <div className="blog-card-grid">
            {candidates.data?.items.map((blog) => {
              const isSaving = replaceLabels.isPending && replaceLabels.variables?.blogId === blog.id;
              return (
                <article key={blog.id} className="blog-card">
                  <div className="blog-card-head">
                    <Link className="card-link" to={`/blogs/${blog.id}`}>
                      <SiteIdentity title={blog.title} domain={blog.domain} iconUrl={blog.icon_url} />
                    </Link>
                    <span className={`status-chip ${blog.is_labeled ? "status-finished" : "status-waiting"}`}>
                      {labelsSummary(blog)}
                    </span>
                  </div>
                  <p className="page-copy">{blog.url}</p>
                  <div className="blog-card-metrics">
                    <span>{labeledHint(blog)}</span>
                    <span>连接线索 {blog.connection_count}</span>
                    <span>抓取状态 {blog.crawl_status}</span>
                  </div>
                  <div className="catalog-checkbox-row">
                    {availableTags.map((tag) => {
                      const active = blog.label_slugs.includes(tag.slug);
                      return (
                        <button
                          key={tag.id}
                          className={active ? "primary-button" : "secondary-button"}
                          disabled={isSaving}
                          onClick={() =>
                            replaceLabels.mutate({
                              blogId: blog.id,
                              tagIds: nextTagIds(blog, tag),
                            })
                          }
                          type="button"
                        >
                          {active ? `已标 ${tag.name}` : `标记 ${tag.name}`}
                        </button>
                      );
                    })}
                    <Link className="button-link secondary-button" to={`/blogs/${blog.id}`}>
                      查看详情
                    </Link>
                  </div>
                </article>
              );
            })}
          </div>
        ) : null}

        {!candidates.isLoading && !candidates.error ? (
          <div className="pagination-row">
            <div className="page-actions">
              <button
                className="secondary-button"
                disabled={!candidates.data?.has_prev}
                onClick={() => changePage(currentPage - 1)}
                type="button"
              >
                上一页
              </button>
              <button
                className="secondary-button"
                disabled={!candidates.data?.has_next}
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
