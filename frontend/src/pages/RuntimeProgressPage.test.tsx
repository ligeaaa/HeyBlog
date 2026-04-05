import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { RuntimeProgressPage } from "./RuntimeProgressPage";
import { useRuntimeStatus } from "../lib/hooks";

vi.mock("../lib/hooks", () => ({
  useRuntimeStatus: vi.fn(),
}));

const mockedUseRuntimeStatus = vi.mocked(useRuntimeStatus);

beforeEach(() => {
  vi.clearAllMocks();
  mockedUseRuntimeStatus.mockReturnValue({
    data: {
      runner_status: "running",
      active_run_id: "run-123",
      worker_count: 3,
      active_workers: 1,
      current_worker_id: "worker-1",
      current_blog_id: 10,
      current_url: "https://blog.example.com/",
      current_stage: "crawling",
      task_started_at: "2026-04-05T15:00:00Z",
      elapsed_seconds: 12.5,
      last_started_at: "2026-04-05T15:00:00Z",
      last_stopped_at: null,
      last_error: null,
      last_result: null,
      workers: [
        {
          worker_id: "worker-1",
          worker_index: 1,
          status: "running",
          current_blog_id: 10,
          current_url: "https://blog.example.com/",
          current_stage: "crawling",
          task_started_at: "2026-04-05T15:00:00Z",
          last_transition_at: "2026-04-05T15:00:00Z",
          last_completed_at: null,
          last_error: null,
          processed: 4,
          discovered: 3,
          failed: 0,
          elapsed_seconds: 12.5,
        },
        {
          worker_id: "worker-2",
          worker_index: 2,
          status: "waiting",
          current_blog_id: null,
          current_url: null,
          current_stage: "waiting_for_work",
          task_started_at: null,
          last_transition_at: "2026-04-05T15:00:05Z",
          last_completed_at: "2026-04-05T15:00:04Z",
          last_error: null,
          processed: 2,
          discovered: 1,
          failed: 0,
          elapsed_seconds: null,
        },
      ],
    },
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useRuntimeStatus>);
});

afterEach(() => {
  cleanup();
});

test("renders crawler worker progress cards", () => {
  render(<RuntimeProgressPage />);

  expect(screen.getByRole("heading", { name: "爬虫进度面板" })).toBeInTheDocument();
  expect(screen.getByText("1/3")).toBeInTheDocument();
  expect(screen.getByText("worker-1")).toBeInTheDocument();
  expect(screen.getByText("正在处理 https://blog.example.com/")).toBeInTheDocument();
  expect(screen.getByText("12.5s")).toBeInTheDocument();
  expect(screen.getByText("worker-2")).toBeInTheDocument();
  expect(screen.getByText("当前空闲")).toBeInTheDocument();
});
