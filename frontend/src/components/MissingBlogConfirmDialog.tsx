import { Loader2 } from "lucide-react";
import { useState } from "react";

interface MissingBlogConfirmDialogProps {
  url: string;
  onCancel: () => void;
  onSubmit: (url: string) => Promise<void>;
}

/**
 * Render a confirmation dialog when a searched blog URL is not recorded.
 *
 * @param url Searched blog URL that was not found.
 * @param onCancel Callback for dismissing the dialog without action.
 * @param onSubmit Callback used to submit the confirmed complete blog URL.
 * @returns Modal confirmation UI.
 */
export function MissingBlogConfirmDialog({ url, onCancel, onSubmit }: MissingBlogConfirmDialogProps) {
  const [isConfirming, setIsConfirming] = useState(false);
  const [seedUrl, setSeedUrl] = useState(url);
  const [isSubmitting, setIsSubmitting] = useState(false);

  /**
   * Submit the user-provided complete URL to the seed ingestion flow.
   *
   * @param event Form submit event.
   */
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!seedUrl.trim()) {
      return;
    }
    setIsSubmitting(true);
    try {
      await onSubmit(seedUrl);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="missing-blog-confirm-title"
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-2xl"
      >
        <h2 id="missing-blog-confirm-title" className="text-xl text-slate-950">
          当前未找到该博客，是否将该博客加入博客网络？
        </h2>
        {isConfirming ? (
          <form onSubmit={handleSubmit} className="mt-5 space-y-4">
            <div>
              <label htmlFor="missing-blog-seed-url" className="mb-2 block text-sm text-slate-700">
                请输入完整博客链接
              </label>
              <input
                id="missing-blog-seed-url"
                type="url"
                value={seedUrl}
                onChange={(event) => setSeedUrl(event.target.value)}
                placeholder="https://blog.example.com"
                disabled={isSubmitting}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none transition-colors placeholder:text-slate-400 focus:border-sky-500 focus:ring-2 focus:ring-sky-100 disabled:cursor-not-allowed disabled:bg-slate-50"
              />
            </div>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={onCancel}
                disabled={isSubmitting}
                className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
              >
                不是
              </button>
              <button
                type="submit"
                disabled={isSubmitting || !seedUrl.trim()}
                className="inline-flex items-center gap-2 rounded-md bg-sky-500 px-4 py-2 text-sm text-white transition-colors hover:bg-sky-600 disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                是
              </button>
            </div>
          </form>
        ) : (
          <>
            <div className="mt-3 break-all text-sm text-slate-500">{url}</div>
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                onClick={onCancel}
                className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-700 transition-colors hover:bg-slate-50"
              >
                不是
              </button>
              <button
                type="button"
                onClick={() => setIsConfirming(true)}
                className="rounded-md bg-sky-500 px-4 py-2 text-sm text-white transition-colors hover:bg-sky-600"
              >
                是
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
