import { Eye, Loader2, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { BlogCard } from "../components/BlogCard";
import { BlogDetailLink } from "../components/BlogDetailLink";
import { Navigation } from "../components/Navigation";
import { readStoredAuthSession } from "../lib/auth";
import { fetchRandomBlogBatch, postBlogUserLabel } from "../lib/api";
import {
  blogInteractionTarget,
  getBlogInteractionSessionId,
  getBlogInteractionVisitorId,
  recordBlogInteraction,
} from "../lib/blogInteractions";
import type { BlogCatalogItem } from "../types/graph";

const RANDOM_BLOG_COUNT = 9;
const RANDOM_PAGE_ENTRANCE_KIND = "random_blog_page";
const RANDOM_LABELS = [
  { slug: "blog", label: "博客" },
  { slug: "company", label: "公司" },
  { slug: "other", label: "其他" },
  { slug: "unknown", label: "未知" },
] as const;

/**
 * Render one standalone page that spotlights a random sample of finished blogs.
 *
 * @returns Random finished-blog discovery page.
 */
export function RandomBlogPage() {
  const [blogs, setBlogs] = useState<BlogCatalogItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [savingLabelKey, setSavingLabelKey] = useState<string | null>(null);
  const [selectedLabelsByUrl, setSelectedLabelsByUrl] = useState<Record<string, string>>({});

  useEffect(() => {
    void loadRandomBlogs({ showInitialLoading: true, showErrorToast: true });
  }, []);

  /**
   * Load a fresh batch of finished blogs in random order.
   *
   * @param options Controls the visible loading state for the fetch.
   * @returns Promise resolved after the page state updates.
   */
  async function loadRandomBlogs(options?: {
    showInitialLoading?: boolean;
    showErrorToast?: boolean;
  }) {
    const showInitialLoading = options?.showInitialLoading ?? false;
    const showErrorToast = options?.showErrorToast ?? true;

    try {
      if (showInitialLoading) {
        setIsLoading(true);
      } else {
        setIsRefreshing(true);
      }
      const session = readStoredAuthSession();
      const response = await fetchRandomBlogBatch({
        count: RANDOM_BLOG_COUNT,
        visitorId: getBlogInteractionVisitorId(),
        sessionId: getBlogInteractionSessionId(),
        source: "random_page",
        pageUrl: window.location.href,
        context: { refresh_kind: showInitialLoading ? "initial" : "manual" },
        token: session?.token,
      });
      setBlogs(response.items);
    } catch {
      if (showErrorToast) {
        toast.error("随机博客加载失败，请稍后再试。");
      }
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }

  /**
   * Save one public feedback label selection for a random blog card.
   *
   * @param blog Blog card receiving the label vote.
   * @param label Label slug selected for this URL.
   * @returns Promise resolved after the vote is saved.
   */
  async function handleUserLabel(blog: BlogCatalogItem, label: string) {
    const selectedLabel = selectedLabelsByUrl[blog.normalizedUrl];
    if (selectedLabel === label) {
      return;
    }
    const key = `${blog.id}:${label}`;
    const session = readStoredAuthSession();
    try {
      setSavingLabelKey(key);
      await postBlogUserLabel(blog.id, label, selectedLabel, session?.token);
      setSelectedLabelsByUrl((current) => ({
        ...current,
        [blog.normalizedUrl]: label,
      }));
      recordBlogInteraction(
        blogInteractionTarget(blog),
        "label_select",
        {
          entranceKind: RANDOM_PAGE_ENTRANCE_KIND,
          entranceUrl: window.location.href,
        },
        { label, previous_label: selectedLabel ?? null },
      );
      toast.success("已记录，谢谢标注。");
    } catch {
      toast.error("标注保存失败，请稍后再试。");
    } finally {
      setSavingLabelKey(null);
    }
  }

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-12 w-12 animate-spin text-sky-500" />
          <div className="text-lg text-slate-600">正在随机挑选博客...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen overflow-x-hidden bg-white">
      <Navigation />

      <main className="mx-auto max-w-7xl px-6 pb-16 pt-24 sm:px-8">
        <section className="mx-auto mb-10 max-w-3xl text-center">
          <p className="mt-4 text-lg leading-8 text-slate-600">
            由于技术原因，目前仍然可能爬取到大量非博客节点
          </p>
          <div className="mt-8 flex items-center justify-center">
            <button
              type="button"
              onClick={() => void loadRandomBlogs({ showInitialLoading: false, showErrorToast: true })}
              disabled={isRefreshing}
              className="inline-flex items-center gap-2 rounded-full border border-sky-200 bg-sky-50 px-5 py-3 text-sm text-sky-700 transition-colors hover:border-sky-300 hover:bg-sky-100 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400"
            >
              {isRefreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              刷新随机博客
            </button>
          </div>
        </section>

        <section className="mb-6 text-center text-sm text-slate-500">
          当前展示 {blogs.length} 个随机博客卡片
        </section>

        <section className="mx-auto grid max-w-6xl grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
          {blogs.map((blog) => (
            <BlogCard
              key={blog.id}
              blog={blog}
              externalEntranceKind={RANDOM_PAGE_ENTRANCE_KIND}
              externalEntranceUrl={window.location.href}
            >
              <BlogDetailLink
                blog={blog}
                entranceKind={RANDOM_PAGE_ENTRANCE_KIND}
                entranceUrl={window.location.href}
                className="mb-3 inline-flex h-10 w-full items-center justify-center gap-2 rounded-md border border-slate-200 bg-slate-950 px-3 text-sm text-white transition-colors hover:bg-slate-800"
              >
                <Eye className="h-4 w-4" />
                查看详情
              </BlogDetailLink>
              <div className="grid grid-cols-4 gap-2">
                {RANDOM_LABELS.map((label) => {
                  const isSaving = savingLabelKey === `${blog.id}:${label.slug}`;
                  const isSelected = selectedLabelsByUrl[blog.normalizedUrl] === label.slug;
                  return (
                    <button
                      key={label.slug}
                      type="button"
                      onClick={() => void handleUserLabel(blog, label.slug)}
                      disabled={savingLabelKey !== null || isSelected}
                      className={[
                        "inline-flex h-10 items-center justify-center rounded-md border px-2 text-sm transition-colors",
                        isSelected
                          ? "border-sky-400 bg-sky-600 text-white shadow-sm shadow-sky-100"
                          : "border-slate-200 bg-white text-slate-700 hover:border-sky-300 hover:bg-sky-50 hover:text-sky-700",
                        "disabled:cursor-not-allowed",
                        !isSelected ? "disabled:bg-slate-100 disabled:text-slate-400" : "",
                      ].join(" ")}
                    >
                      {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : label.label}
                    </button>
                  );
                })}
              </div>
            </BlogCard>
          ))}
        </section>
      </main>
    </div>
  );
}
