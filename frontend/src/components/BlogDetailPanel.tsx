import { ArrowLeft, ArrowRight, ExternalLink, Sparkles, X } from "lucide-react";
import type { BlogDetail } from "../types/graph";

interface BlogDetailPanelProps {
  detail: BlogDetail;
  onClose: () => void;
}

/**
 * Render the selected blog detail using normalized backend payloads.
 *
 * @param detail Selected blog detail payload.
 * @param onClose Callback used to dismiss the panel.
 * @returns Floating detail panel.
 */
export function BlogDetailPanel({ detail, onClose }: BlogDetailPanelProps) {
  return (
    <div className="absolute right-8 top-24 z-10 max-h-[70vh] w-96 overflow-y-auto rounded-lg border-2 border-gray-200 bg-white p-6 shadow-2xl">
      <div className="mb-4 flex items-start justify-between">
        <div className="pr-8">
          <h3 className="text-xl text-gray-900">{detail.title || detail.domain}</h3>
          <div className="mt-1 text-sm text-gray-500">{detail.domain}</div>
        </div>
        <button onClick={onClose} className="flex-shrink-0 rounded-md p-1 transition-colors hover:bg-gray-100">
          <X className="h-5 w-5 text-gray-600" />
        </button>
      </div>

      <div className="space-y-4">
        <div>
          <div className="mb-1 text-sm text-gray-600">URL</div>
          <a
            href={detail.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 break-all text-blue-600 hover:underline"
          >
            {detail.url}
            <ExternalLink className="h-4 w-4 flex-shrink-0" />
          </a>
        </div>

        <div className="border-t border-gray-200 pt-4">
          <div className="mb-3 text-sm text-gray-600">连接统计</div>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg bg-purple-50 p-3">
              <div className="mb-1 flex items-center gap-1 text-purple-700">
                <ArrowLeft className="h-4 w-4" />
                <span className="text-sm">入链</span>
              </div>
              <div className="text-2xl text-purple-600">{detail.incomingLinks}</div>
            </div>
            <div className="rounded-lg bg-orange-50 p-3">
              <div className="mb-1 flex items-center gap-1 text-orange-700">
                <ArrowRight className="h-4 w-4" />
                <span className="text-sm">出链</span>
              </div>
              <div className="text-2xl text-orange-600">{detail.outgoingLinks}</div>
            </div>
          </div>
        </div>

        {detail.relatedNodes.length > 0 ? (
          <div className="border-t border-gray-200 pt-4">
            <div className="mb-2 text-sm text-gray-600">直接相关博客</div>
            <div className="space-y-2">
              {detail.relatedNodes.slice(0, 5).map((node) => (
                <div key={node.id} className="rounded bg-gray-50 p-2 text-sm">
                  <div className="mb-1 text-gray-900">{node.title || node.domain}</div>
                  <div className="truncate text-xs text-gray-500">{node.domain}</div>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {detail.recommendedBlogs.length > 0 ? (
          <div className="border-t border-gray-200 pt-4">
            <div className="mb-2 flex items-center gap-1 text-sm text-gray-600">
              <Sparkles className="h-4 w-4" />
              推荐博客
            </div>
            <div className="space-y-2">
              {detail.recommendedBlogs.slice(0, 4).map((blog) => (
                <div key={blog.id} className="rounded bg-blue-50 p-3 text-sm">
                  <div className="text-gray-900">{blog.title || blog.domain}</div>
                  <div className="mt-1 truncate text-xs text-gray-500">{blog.domain}</div>
                  {blog.viaBlogs.length > 0 ? (
                    <div className="mt-2 text-xs text-blue-700">
                      通过 {blog.viaBlogs.map((viaBlog) => viaBlog.title || viaBlog.domain).join("、")} 关联
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
