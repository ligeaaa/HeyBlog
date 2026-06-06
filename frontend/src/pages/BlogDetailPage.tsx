import { ArrowLeft, ArrowRight, ArrowUpRight, GitBranch, Loader2, Network, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Navigation } from "../components/Navigation";
import { fetchBlogDetail } from "../lib/api";
import { resolveBlogIconUrls } from "../lib/icon";
import type { BlogDetail, GraphNode, RecommendedBlog } from "../types/graph";

/**
 * Format a numeric count for compact detail cards.
 *
 * @param value Count value to display.
 * @returns Localized count string.
 */
function formatCount(value: number) {
  return new Intl.NumberFormat("zh-CN").format(value);
}

/**
 * Render one compact blog link in related and recommendation lists.
 *
 * @param props Blog row and optional supporting copy.
 * @returns Clickable blog summary row.
 */
function BlogListItem({ blog, helperText }: { blog: GraphNode | RecommendedBlog; helperText?: string }) {
  return (
    <Link
      to={`/blogs/${blog.id}`}
      className="block rounded-lg border border-slate-200 bg-white px-4 py-3 transition-colors hover:border-sky-300 hover:bg-sky-50"
    >
      <div className="min-w-0">
        <div className="truncate text-sm font-medium text-slate-950">{blog.title || blog.domain}</div>
        <div className="mt-1 truncate text-xs text-slate-500">{blog.domain}</div>
        {helperText ? <div className="mt-2 text-xs leading-5 text-sky-700">{helperText}</div> : null}
      </div>
    </Link>
  );
}

/**
 * Render a detail page hero icon with favicon fallbacks.
 *
 * @param props Blog detail node used to resolve icon candidates.
 * @returns Blog icon image or a text fallback.
 */
function BlogHeroIcon({ detail }: { detail: BlogDetail }) {
  const iconUrls = resolveBlogIconUrls(detail);
  const [iconIndex, setIconIndex] = useState(0);
  const iconUrl = iconUrls[iconIndex];

  useEffect(() => {
    setIconIndex(0);
  }, [detail.id, detail.iconUrl, detail.url, detail.domain]);

  return (
    <div className="mb-4 flex h-16 w-16 items-center justify-center overflow-hidden rounded-lg bg-sky-100 text-2xl font-semibold text-sky-700 ring-1 ring-sky-200">
      {iconUrl ? (
        <img
          src={iconUrl}
          alt={`${detail.domain} icon`}
          className="h-full w-full object-cover"
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setIconIndex((currentIndex) => currentIndex + 1)}
        />
      ) : (
        <span>{(detail.domain || "?").slice(0, 1).toUpperCase()}</span>
      )}
    </div>
  );
}

/**
 * Render the public blog detail page.
 *
 * @returns Blog detail route UI.
 */
export function BlogDetailPage() {
  const { blogId } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<BlogDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const numericBlogId = Number(blogId);
  const relatedBlogs = detail?.relatedNodes ?? [];
  const recommendedBlogs = detail?.recommendedBlogs ?? [];

  useEffect(() => {
    let isDisposed = false;

    /**
     * Load the route blog detail payload.
     *
     * @returns Promise resolved when detail state settles.
     */
    async function loadDetail() {
      if (!Number.isInteger(numericBlogId) || numericBlogId <= 0) {
        setErrorMessage("博客 ID 无效。");
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      setErrorMessage(null);
      try {
        const payload = await fetchBlogDetail(numericBlogId);
        if (!isDisposed) {
          setDetail(payload);
        }
      } catch {
        if (!isDisposed) {
          setDetail(null);
          setErrorMessage("博客详情加载失败。");
          toast.error("博客详情加载失败，请稍后重试。");
        }
      } finally {
        if (!isDisposed) {
          setIsLoading(false);
        }
      }
    }

    void loadDetail();
    return () => {
      isDisposed = true;
    };
  }, [numericBlogId]);

  return (
    <div className="min-h-screen overflow-x-hidden bg-white">
      <Navigation />
      <main className="mx-auto max-w-6xl px-6 pb-16 pt-24 sm:px-8">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="mb-8 inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600 transition-colors hover:border-sky-300 hover:text-sky-700"
        >
          <ArrowLeft className="h-4 w-4" />
          返回
        </button>

        {isLoading ? (
          <section className="flex min-h-[360px] items-center justify-center">
            <div className="flex flex-col items-center gap-4 text-slate-500">
              <Loader2 className="h-10 w-10 animate-spin text-sky-500" />
              <div>正在加载博客详情...</div>
            </div>
          </section>
        ) : null}

        {!isLoading && errorMessage ? (
          <section className="rounded-lg border border-rose-200 bg-rose-50 px-6 py-8 text-rose-700">
            {errorMessage}
          </section>
        ) : null}

        {!isLoading && detail ? (
          <div className="space-y-8">
            <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
                <div className="min-w-0">
                  <BlogHeroIcon detail={detail} />
                  <h1 className="break-words text-4xl leading-tight text-slate-950">{detail.title || detail.domain}</h1>
                  <div className="mt-2 text-base text-slate-500">{detail.domain}</div>
                  <a
                    href={detail.url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-4 inline-flex max-w-full items-center gap-2 break-all text-sm text-sky-700 hover:underline"
                  >
                    {detail.url}
                    <ArrowUpRight className="h-4 w-4 flex-shrink-0" />
                  </a>
                </div>
              </div>
            </section>

            <section className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-sky-100 text-sky-700">
                  <ArrowLeft className="h-5 w-5" />
                </div>
                <div className="text-sm text-slate-500">入链</div>
                <div className="mt-2 text-3xl text-slate-950">{formatCount(detail.incomingLinks)}</div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-100 text-emerald-700">
                  <ArrowRight className="h-5 w-5" />
                </div>
                <div className="text-sm text-slate-500">出链</div>
                <div className="mt-2 text-3xl text-slate-950">{formatCount(detail.outgoingLinks)}</div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-violet-100 text-violet-700">
                  <Network className="h-5 w-5" />
                </div>
                <div className="text-sm text-slate-500">直接相关博客</div>
                <div className="mt-2 text-3xl text-slate-950">{formatCount(relatedBlogs.length)}</div>
              </div>
            </section>

            <section className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
              <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
                <div className="mb-4 flex items-center gap-2">
                  <GitBranch className="h-5 w-5 text-slate-500" />
                  <h2 className="text-xl text-slate-950">直接相关博客</h2>
                </div>
                {relatedBlogs.length > 0 ? (
                  <div className="grid max-h-[520px] gap-3 overflow-y-auto pr-1 sm:grid-cols-2">
                    {relatedBlogs.map((blog) => (
                      <BlogListItem key={blog.id} blog={blog} />
                    ))}
                  </div>
                ) : (
                  <div className="rounded-lg bg-slate-50 px-4 py-8 text-sm text-slate-500">暂无直接相关博客。</div>
                )}
              </div>

              <aside className="space-y-6">
                <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="mb-4 flex items-center gap-2">
                    <Sparkles className="h-5 w-5 text-sky-600" />
                    <h2 className="text-xl text-slate-950">推荐博客</h2>
                  </div>
                  {recommendedBlogs.length > 0 ? (
                    <div className="space-y-3">
                      {recommendedBlogs.slice(0, 6).map((blog) => (
                        <BlogListItem
                          key={blog.id}
                          blog={blog}
                          helperText={
                            blog.viaBlogs.length > 0
                              ? `通过 ${blog.viaBlogs.map((viaBlog) => viaBlog.title || viaBlog.domain).join("、")} 关联`
                              : undefined
                          }
                        />
                      ))}
                    </div>
                  ) : (
                    <div className="rounded-lg bg-slate-50 px-4 py-6 text-sm text-slate-500">暂无推荐博客。</div>
                  )}
                </section>

                <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
                  <h2 className="text-xl text-slate-950">基础信息</h2>
                  <dl className="mt-4 space-y-3 text-sm">
                    <div>
                      <dt className="text-slate-500">Blog ID</dt>
                      <dd className="mt-1 text-slate-950">{detail.id}</dd>
                    </div>
                    <div>
                      <dt className="text-slate-500">域名</dt>
                      <dd className="mt-1 break-all text-slate-950">{detail.domain}</dd>
                    </div>
                    <div>
                      <dt className="text-slate-500">URL</dt>
                      <dd className="mt-1 break-all text-slate-950">{detail.url}</dd>
                    </div>
                  </dl>
                </section>
              </aside>
            </section>
          </div>
        ) : null}
      </main>
    </div>
  );
}
