import { Dices, Loader2, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { BlogCard } from "../components/BlogCard";
import { Navigation } from "../components/Navigation";
import { fetchBlogsCatalog } from "../lib/api";
import type { BlogCatalogItem } from "../types/graph";

const RANDOM_BLOG_COUNT = 9;

/**
 * Render one standalone page that spotlights a random sample of finished blogs.
 *
 * @returns Random finished-blog discovery page.
 */
export function RandomBlogPage() {
  const [blogs, setBlogs] = useState<BlogCatalogItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

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
      const response = await fetchBlogsCatalog({
        page: 1,
        pageSize: RANDOM_BLOG_COUNT,
        status: "FINISHED",
        sort: "random",
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
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-sky-200 bg-white/90 px-4 py-2 text-sm text-sky-700 shadow-sm">
            <Dices className="h-4 w-4" />
            Random Finished Blogs
          </div>
          <h1 className="text-4xl leading-tight text-slate-950 sm:text-5xl">随机发现 9 个已完成抓取的博客</h1>
          <p className="mt-4 text-lg leading-8 text-slate-600">
            每次刷新都会从状态为 <code>FINISHED</code> 的博客中重新抽取 9 个，帮你快速逛到不一样的站点。
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
            <BlogCard key={blog.id} blog={blog} />
          ))}
        </section>
      </main>
    </div>
  );
}
