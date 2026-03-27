import { FormEvent, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { Surface } from "../components/Surface";
import { useCrawlerActions, useRuntimeStatus } from "../lib/hooks";

export function ControlPage() {
  const runtime = useRuntimeStatus();
  const actions = useCrawlerActions();
  const [batchCount, setBatchCount] = useState("10");
  const [message, setMessage] = useState("Ready.");

  const handleRunBatch = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const maxNodes = Number(batchCount);
      const result = await actions.runBatch.mutateAsync(maxNodes);
      setMessage(`run-batch complete: ${JSON.stringify(result)}`);
    } catch (error) {
      setMessage(`run-batch failed: ${(error as Error).message}`);
    }
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Control"
        title="控制界面"
        description="控制 crawler 开启、关闭，或触发新的 N 个 blog 批处理。"
      />
      <Surface title="当前运行态" note="来自 /api/runtime/status">
        <p className="status-line">runner_status: {runtime.data?.runner_status ?? "idle"}</p>
        <div className="action-row">
          <button
            className="primary-button"
            disabled={actions.start.isPending}
            onClick={async () => {
              try {
                const result = await actions.start.mutateAsync();
                setMessage(`start: ${JSON.stringify(result)}`);
              } catch (error) {
                setMessage(`start failed: ${(error as Error).message}`);
              }
            }}
          >
            开启爬虫
          </button>
          <button
            className="secondary-button"
            disabled={actions.stop.isPending}
            onClick={async () => {
              try {
                const result = await actions.stop.mutateAsync();
                setMessage(`stop: ${JSON.stringify(result)}`);
              } catch (error) {
                setMessage(`stop failed: ${(error as Error).message}`);
              }
            }}
          >
            停止爬虫
          </button>
          <button
            className="secondary-button"
            disabled={actions.bootstrap.isPending}
            onClick={async () => {
              try {
                const result = await actions.bootstrap.mutateAsync();
                setMessage(`bootstrap: ${JSON.stringify(result)}`);
              } catch (error) {
                setMessage(`bootstrap failed: ${(error as Error).message}`);
              }
            }}
          >
            导入 Seed
          </button>
        </div>
      </Surface>
      <Surface title="批量爬取 N 个 blog">
        <form className="batch-form" onSubmit={handleRunBatch}>
          <label>
            <span>Max nodes</span>
            <input
              type="number"
              min="1"
              value={batchCount}
              onChange={(event) => setBatchCount(event.target.value)}
            />
          </label>
          <button className="primary-button" disabled={actions.runBatch.isPending} type="submit">
            爬取新的 N 个 blog
          </button>
        </form>
      </Surface>
      <Surface title="操作结果">
        <p>{message}</p>
      </Surface>
    </div>
  );
}
