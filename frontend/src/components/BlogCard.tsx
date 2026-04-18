import { ArrowUpRight, CheckCircle2, Clock3, XCircle } from "lucide-react";
import type { BlogCatalogItem } from "../types/graph";

interface BlogCardProps {
  blog: BlogCatalogItem;
}

function statusTone(crawlStatus: string) {
  switch (crawlStatus) {
    case "FINISHED":
      return {
        label: "FINISHED",
        className: "bg-emerald-100 text-emerald-700",
        icon: CheckCircle2,
      };
    case "PROCESSING":
      return {
        label: "PROCESSING",
        className: "bg-amber-100 text-amber-700",
        icon: Clock3,
      };
    case "FAILED":
      return {
        label: "FAILED",
        className: "bg-rose-100 text-rose-700",
        icon: XCircle,
      };
    default:
      return {
        label: "WAITING",
        className: "bg-slate-200 text-slate-700",
        icon: Clock3,
      };
  }
}

/**
 * Render one catalog blog card in the example-inspired home layout.
 *
 * @param blog Catalog row returned by `/api/blogs/catalog`.
 * @returns Blog summary card.
 */
export function BlogCard({ blog }: BlogCardProps) {
  const tone = statusTone(blog.crawlStatus);
  const ToneIcon = tone.icon;

  return (
    <article className="group flex h-full flex-col rounded-[28px] border border-slate-200/80 bg-white/95 p-6 shadow-[0_18px_40px_rgba(15,23,42,0.08)] transition-all duration-300 hover:-translate-y-1 hover:border-sky-300 hover:shadow-[0_26px_60px_rgba(14,165,233,0.18)]">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-center gap-4">
          <div className="flex h-14 w-14 flex-shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-slate-100 ring-1 ring-slate-200">
            {blog.iconUrl ? (
              <img src={blog.iconUrl} alt={blog.title || blog.domain} className="h-full w-full object-cover" />
            ) : (
              <span className="text-lg text-slate-500">{(blog.domain || "?").slice(0, 1).toUpperCase()}</span>
            )}
          </div>
          <div className="min-w-0">
            <h3 className="truncate text-xl text-slate-900">{blog.title || blog.domain}</h3>
          </div>
        </div>
        <span className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs ${tone.className}`}>
          <ToneIcon className="h-3.5 w-3.5" />
          {tone.label}
        </span>
      </div>

      <div className="flex items-center justify-between gap-3 rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
        <div className="min-w-0 truncate">{blog.url}</div>
        <a
          href={blog.url}
          target="_blank"
          rel="noreferrer"
          aria-label={`打开 ${blog.title || blog.domain}`}
          className="inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 transition-colors duration-200 hover:border-sky-300 hover:text-sky-600"
        >
          <ArrowUpRight className="h-4 w-4" />
        </a>
      </div>
    </article>
  );
}
