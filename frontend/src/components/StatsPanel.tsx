import { GitBranch, Network } from "lucide-react";

interface StatsPanelProps {
  totalNodes: number;
  totalEdges: number;
}

/**
 * Render the example footer statistics section.
 *
 * @param totalNodes Total node count.
 * @param totalEdges Total edge count.
 * @returns Example-aligned statistics panel.
 */
export function StatsPanel({ totalNodes, totalEdges }: StatsPanelProps) {
  return (
    <div className="w-full border-t-2 border-gray-200 bg-white px-8 py-6">
      <div className="mx-auto max-w-6xl">
        <h2 className="mb-4 text-xl text-gray-700">数据统计</h2>
        <div className="grid grid-cols-2 gap-8">
          <div className="flex items-center gap-4 rounded-lg bg-blue-50 p-4">
            <div className="rounded-full bg-blue-500 p-3">
              <Network className="h-6 w-6 text-white" />
            </div>
            <div>
              <div className="text-sm text-gray-600">总节点数</div>
              <div className="text-3xl text-blue-600">{totalNodes}</div>
            </div>
          </div>

          <div className="flex items-center gap-4 rounded-lg bg-green-50 p-4">
            <div className="rounded-full bg-green-500 p-3">
              <GitBranch className="h-6 w-6 text-white" />
            </div>
            <div>
              <div className="text-sm text-gray-600">总边数</div>
              <div className="text-3xl text-green-600">{totalEdges}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
