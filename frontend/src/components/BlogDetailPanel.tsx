import { ArrowLeft, ArrowRight, ExternalLink, Tag, User, X } from "lucide-react";
import type { BlogDetail } from "../types/graph";

interface BlogDetailPanelProps {
  detail: BlogDetail;
  onClose: () => void;
}

/**
 * Render the example detail side panel for the selected blog.
 *
 * @param detail Selected blog detail payload.
 * @param onClose Callback used to dismiss the panel.
 * @returns Floating detail panel.
 */
export function BlogDetailPanel({ detail, onClose }: BlogDetailPanelProps) {
  return (
    <div className="absolute right-8 top-24 z-10 max-h-[70vh] w-96 overflow-y-auto rounded-lg border-2 border-gray-200 bg-white p-6 shadow-2xl">
      <div className="mb-4 flex items-start justify-between">
        <h3 className="pr-8 text-xl text-gray-900">{detail.title || "博客详情"}</h3>
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

        {detail.author ? (
          <div>
            <div className="mb-1 flex items-center gap-1 text-sm text-gray-600">
              <User className="h-4 w-4" />
              作者
            </div>
            <div className="text-gray-900">{detail.author}</div>
          </div>
        ) : null}

        {detail.description ? (
          <div>
            <div className="mb-1 text-sm text-gray-600">描述</div>
            <div className="text-gray-900">{detail.description}</div>
          </div>
        ) : null}

        {detail.tags && detail.tags.length > 0 ? (
          <div>
            <div className="mb-2 flex items-center gap-1 text-sm text-gray-600">
              <Tag className="h-4 w-4" />
              标签
            </div>
            <div className="flex flex-wrap gap-2">
              {detail.tags.map((tag) => (
                <span key={tag} className="rounded-full bg-blue-100 px-3 py-1 text-sm text-blue-700">
                  {tag}
                </span>
              ))}
            </div>
          </div>
        ) : null}

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
            <div className="mb-2 text-sm text-gray-600">相关博客</div>
            <div className="space-y-2">
              {detail.relatedNodes.slice(0, 5).map((node) => (
                <div key={node.id} className="rounded bg-gray-50 p-2 text-sm">
                  <div className="mb-1 text-gray-900">{node.title || "Untitled"}</div>
                  <div className="truncate text-xs text-gray-500">{node.url}</div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
