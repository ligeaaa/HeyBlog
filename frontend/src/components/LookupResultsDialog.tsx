import { X } from "lucide-react";
import type { GraphNode } from "../types/graph";

interface LookupResultsDialogProps {
  items: GraphNode[];
  onClose: () => void;
  onSelect: (item: GraphNode) => void;
}

/**
 * Render a disambiguation modal when one lookup URL maps to multiple blogs.
 *
 * @param items Matching lookup candidates.
 * @param onClose Callback used to dismiss the dialog.
 * @param onSelect Callback used when one candidate is chosen.
 * @returns Modal list UI.
 */
export function LookupResultsDialog({ items, onClose, onSelect }: LookupResultsDialogProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-xl rounded-lg bg-white p-6 shadow-2xl">
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="text-2xl text-gray-900">找到多个候选博客</h2>
            <div className="mt-1 text-sm text-gray-500">请选择你要查看的目标博客。</div>
          </div>
          <button onClick={onClose} className="rounded-md p-1 transition-colors hover:bg-gray-100">
            <X className="h-5 w-5 text-gray-600" />
          </button>
        </div>

        <div className="space-y-3">
          {items.map((item) => (
            <button
              key={item.id}
              onClick={() => onSelect(item)}
              className="block w-full rounded-lg border border-gray-200 p-4 text-left transition-colors hover:border-blue-300 hover:bg-blue-50"
            >
              <div className="text-gray-900">{item.title || item.domain}</div>
              <div className="mt-1 text-sm text-gray-500">{item.url}</div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
