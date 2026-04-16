import { useState } from "react";
import { AlertCircle, X } from "lucide-react";
import { toast } from "sonner";
import { submitBlogInfo } from "../lib/api";

interface SubmitBlogDialogProps {
  url: string;
  onClose: () => void;
  onSuccess?: () => void;
}

/**
 * Render the example modal shown when a searched URL is absent from the fake graph.
 *
 * @param url Missing URL being submitted.
 * @param onClose Callback used to dismiss the modal.
 * @param onSuccess Optional callback after a successful submit.
 * @returns Modal dialog UI.
 */
export function SubmitBlogDialog({ url, onClose, onSuccess }: SubmitBlogDialogProps) {
  const [formData, setFormData] = useState({
    title: "",
    description: "",
    author: "",
    tags: "",
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  /**
   * Submit the current fake blog payload.
   *
   * @param event Form submit event.
   */
  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    try {
      setIsSubmitting(true);
      await submitBlogInfo({
        url,
        title: formData.title || undefined,
        description: formData.description || undefined,
        author: formData.author || undefined,
        tags: formData.tags
          ? formData.tags
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean)
          : undefined,
      });

      toast.success("fake submit 已记录，后续再接回真实后端。");
      onSuccess?.();
      onClose();
    } catch {
      toast.error("提交失败，请稍后重试。");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg bg-white shadow-2xl">
        <div className="sticky top-0 flex items-start justify-between border-b border-gray-200 bg-white p-6">
          <div>
            <h2 className="mb-2 text-2xl text-gray-900">博客未找到</h2>
            <div className="flex items-start gap-2 rounded-md bg-amber-50 p-3 text-amber-700">
              <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0" />
              <div className="text-sm">该 URL 当前不在 fake graph 中，可以先走示例表单流程。</div>
            </div>
          </div>
          <button onClick={onClose} className="flex-shrink-0 rounded-md p-1 transition-colors hover:bg-gray-100">
            <X className="h-6 w-6 text-gray-600" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5 p-6">
          <div>
            <label className="mb-2 block text-sm text-gray-700">
              URL <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={url}
              disabled
              className="w-full rounded-md border border-gray-300 bg-gray-50 px-4 py-2 text-gray-600"
            />
          </div>

          <div>
            <label className="mb-2 block text-sm text-gray-700">博客标题</label>
            <input
              type="text"
              value={formData.title}
              onChange={(event) => setFormData({ ...formData, title: event.target.value })}
              placeholder="例如：深度学习入门指南"
              className="w-full rounded-md border border-gray-300 px-4 py-2 focus:border-blue-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-2 block text-sm text-gray-700">描述</label>
            <textarea
              value={formData.description}
              onChange={(event) => setFormData({ ...formData, description: event.target.value })}
              placeholder="简要描述博客内容..."
              rows={3}
              className="w-full resize-none rounded-md border border-gray-300 px-4 py-2 focus:border-blue-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-2 block text-sm text-gray-700">作者</label>
            <input
              type="text"
              value={formData.author}
              onChange={(event) => setFormData({ ...formData, author: event.target.value })}
              placeholder="作者名称"
              className="w-full rounded-md border border-gray-300 px-4 py-2 focus:border-blue-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-2 block text-sm text-gray-700">标签</label>
            <input
              type="text"
              value={formData.tags}
              onChange={(event) => setFormData({ ...formData, tags: event.target.value })}
              placeholder="用逗号分隔，例如：React, TypeScript, Frontend"
              className="w-full rounded-md border border-gray-300 px-4 py-2 focus:border-blue-500 focus:outline-none"
            />
          </div>

          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-md border-2 border-gray-300 px-6 py-3 text-gray-700 transition-colors hover:bg-gray-50"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex-1 rounded-md bg-blue-500 px-6 py-3 text-white transition-colors hover:bg-blue-600 disabled:cursor-not-allowed disabled:bg-gray-300"
            >
              {isSubmitting ? "提交中..." : "提交信息"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
