import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ControlPage } from "./ControlPage";
import {
  useBlogDedupScanRunItems,
  useCrawlerActions,
  useLatestBlogDedupScanRun,
  useRunBlogDedupScan,
  useRuntimeStatus,
} from "../lib/hooks";

vi.mock("../lib/hooks", () => ({
  useBlogDedupScanRunItems: vi.fn(),
  useCrawlerActions: vi.fn(),
  useLatestBlogDedupScanRun: vi.fn(),
  useRunBlogDedupScan: vi.fn(),
  useRuntimeStatus: vi.fn(),
}));

const mockedUseBlogDedupScanRunItems = vi.mocked(useBlogDedupScanRunItems);
const mockedUseCrawlerActions = vi.mocked(useCrawlerActions);
const mockedUseLatestBlogDedupScanRun = vi.mocked(useLatestBlogDedupScanRun);
const mockedUseRunBlogDedupScan = vi.mocked(useRunBlogDedupScan);
const mockedUseRuntimeStatus = vi.mocked(useRuntimeStatus);

function buildActions() {
  return {
    bootstrap: { isPending: false, mutateAsync: vi.fn() },
    start: { isPending: false, mutateAsync: vi.fn() },
    stop: { isPending: false, mutateAsync: vi.fn() },
    runBatch: { isPending: false, mutateAsync: vi.fn() },
    resetDatabase: {
      isPending: false,
      mutateAsync: vi.fn().mockResolvedValue({
        ok: true,
        blogs_deleted: 2,
        edges_deleted: 1,
        logs_deleted: 0,
        search_reindexed: true,
        search: null,
      }),
    },
  };
}

function buildScanAction() {
  return {
    isPending: false,
    mutateAsync: vi.fn().mockResolvedValue({
      id: 1,
      status: "RUNNING",
      total_count: 3,
      scanned_count: 3,
      kept_count: 1,
      removed_count: 2,
    }),
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedUseRuntimeStatus.mockReturnValue({
    data: { runner_status: "idle", maintenance_in_progress: false },
    isLoading: false,
  } as unknown as ReturnType<typeof useRuntimeStatus>);
  mockedUseCrawlerActions.mockReturnValue(
    buildActions() as unknown as ReturnType<typeof useCrawlerActions>,
  );
  mockedUseRunBlogDedupScan.mockReturnValue(
    buildScanAction() as unknown as ReturnType<typeof useRunBlogDedupScan>,
  );
  mockedUseLatestBlogDedupScanRun.mockReturnValue({
    data: undefined,
  } as unknown as ReturnType<typeof useLatestBlogDedupScanRun>);
  mockedUseBlogDedupScanRunItems.mockReturnValue({
    data: [],
  } as unknown as ReturnType<typeof useBlogDedupScanRunItems>);
});

afterEach(() => {
  cleanup();
});

test("disables database reset while crawler is busy", () => {
  mockedUseRuntimeStatus.mockReturnValue({
    data: { runner_status: "running", maintenance_in_progress: false },
    isLoading: false,
  } as unknown as ReturnType<typeof useRuntimeStatus>);

  render(<ControlPage />);

  expect(screen.getByRole("button", { name: "重置数据库" })).toBeDisabled();
});

test("confirms and triggers database reset", async () => {
  const actions = buildActions();
  mockedUseCrawlerActions.mockReturnValue(
    actions as unknown as ReturnType<typeof useCrawlerActions>,
  );
  const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

  render(<ControlPage />);
  await userEvent.click(screen.getByRole("button", { name: "重置数据库" }));

  expect(confirmSpy).toHaveBeenCalled();
  expect(actions.resetDatabase.mutateAsync).toHaveBeenCalled();
  const resultSection = screen.getByRole("heading", { name: "操作结果" }).closest("section");
  expect(resultSection).not.toBeNull();
  expect(await within(resultSection as HTMLElement).findByText(/database reset:/i)).toBeInTheDocument();

  confirmSpy.mockRestore();
});

test("shows latest dedup scan summary and removed item details", () => {
  mockedUseLatestBlogDedupScanRun.mockReturnValue({
    data: {
      id: 9,
      status: "SUCCEEDED",
      total_count: 3,
      scanned_count: 3,
      kept_count: 1,
      removed_count: 2,
      duration_ms: 12,
      crawler_restart_attempted: true,
      crawler_restart_succeeded: true,
      search_reindexed: true,
      error_message: null,
    },
  } as unknown as ReturnType<typeof useLatestBlogDedupScanRun>);
  mockedUseBlogDedupScanRunItems.mockReturnValue({
    data: [
      {
        id: 1,
        removed_url: "http://blog.langhai.cc",
        reason_code: "blog_alias_collapsed",
        survivor_selection_basis: "FINISHED, created_at=2026-04-05T00:00:00Z, id=1",
      },
    ],
  } as unknown as ReturnType<typeof useBlogDedupScanRunItems>);

  render(<ControlPage />);

  expect(screen.getByText(/扫描进度：已扫描节点 3 \/ 总共节点 3/i)).toBeInTheDocument();
  expect(screen.getByText(/最近一次扫描：status=SUCCEEDED/i)).toBeInTheDocument();
  expect(screen.getByText("http://blog.langhai.cc")).toBeInTheDocument();
  expect(screen.getByText("blog_alias_collapsed")).toBeInTheDocument();
});

test("shows running scan progress and disables the scan button", () => {
  mockedUseLatestBlogDedupScanRun.mockReturnValue({
    data: {
      id: 11,
      status: "RUNNING",
      total_count: 12,
      scanned_count: 5,
      kept_count: 3,
      removed_count: 2,
      duration_ms: 120,
      crawler_restart_attempted: false,
      crawler_restart_succeeded: false,
      search_reindexed: false,
      error_message: null,
    },
  } as unknown as ReturnType<typeof useLatestBlogDedupScanRun>);

  render(<ControlPage />);

  expect(screen.getByRole("button", { name: "全库规则重扫进行中" })).toBeDisabled();
  expect(screen.getByText(/扫描进度：已扫描节点 5 \/ 总共节点 12/i)).toBeInTheDocument();
});
