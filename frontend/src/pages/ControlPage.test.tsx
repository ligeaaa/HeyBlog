import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ControlPage } from "./ControlPage";
import { useCrawlerActions, useRuntimeStatus } from "../lib/hooks";

vi.mock("../lib/hooks", () => ({
  useCrawlerActions: vi.fn(),
  useRuntimeStatus: vi.fn(),
}));

const mockedUseCrawlerActions = vi.mocked(useCrawlerActions);
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

beforeEach(() => {
  vi.clearAllMocks();
  mockedUseRuntimeStatus.mockReturnValue({
    data: { runner_status: "idle" },
    isLoading: false,
  } as unknown as ReturnType<typeof useRuntimeStatus>);
  mockedUseCrawlerActions.mockReturnValue(
    buildActions() as unknown as ReturnType<typeof useCrawlerActions>,
  );
});

afterEach(() => {
  cleanup();
});

test("disables database reset while crawler is busy", () => {
  mockedUseRuntimeStatus.mockReturnValue({
    data: { runner_status: "running" },
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
  expect(await screen.findByText(/database reset:/i)).toBeInTheDocument();

  confirmSpy.mockRestore();
});
