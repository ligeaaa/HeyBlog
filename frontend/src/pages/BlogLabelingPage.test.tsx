import { cleanup, render, screen, waitFor, act, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { BlogLabelingPage } from "./BlogLabelingPage";
import {
  useBlogLabelingCandidates,
  useCreateBlogLabelTag,
  useExportBlogLabelTrainingCsv,
  useReplaceBlogLinkLabels,
} from "../lib/hooks";

vi.mock("../lib/hooks", () => ({
  useBlogLabelingCandidates: vi.fn(),
  useCreateBlogLabelTag: vi.fn(),
  useExportBlogLabelTrainingCsv: vi.fn(),
  useReplaceBlogLinkLabels: vi.fn(),
}));

const mockedUseBlogLabelingCandidates = vi.mocked(useBlogLabelingCandidates);
const mockedUseCreateBlogLabelTag = vi.mocked(useCreateBlogLabelTag);
const mockedUseExportBlogLabelTrainingCsv = vi.mocked(useExportBlogLabelTrainingCsv);
const mockedUseReplaceBlogLinkLabels = vi.mocked(useReplaceBlogLinkLabels);

function buildCandidatesData(
  page = 1,
  filters?: {
    q?: string | null;
    label?: string | null;
    labeled?: boolean | null;
    sort?: string;
  },
) {
  return {
    items: [
      {
        id: 1,
        url: "https://alpha.example/",
        normalized_url: "https://alpha.example/",
        domain: "alpha.example",
        email: null,
        title: "Alpha Blog",
        icon_url: "https://alpha.example/favicon.ico",
        status_code: 200,
        crawl_status: "FINISHED",
        friend_links_count: 3,
        last_crawled_at: null,
        created_at: "2026-03-31T00:00:00Z",
        updated_at: "2026-03-31T00:00:00Z",
        incoming_count: 2,
        outgoing_count: 1,
        connection_count: 3,
        activity_at: "2026-03-31T00:00:00Z",
        identity_complete: true,
        labels: [],
        label_slugs: [],
        last_labeled_at: null,
        is_labeled: filters?.labeled ?? false,
      },
    ],
    available_tags: [
      {
        id: 10,
        name: "blog",
        slug: "blog",
        created_at: "2026-04-05T00:00:00Z",
        updated_at: "2026-04-05T00:00:00Z",
      },
      {
        id: 11,
        name: "official",
        slug: "official",
        created_at: "2026-04-05T00:00:00Z",
        updated_at: "2026-04-05T00:00:00Z",
      },
    ],
    page,
    page_size: 50,
    total_items: 1,
    total_pages: 1,
    has_next: false,
    has_prev: false,
    filters: {
      q: filters?.q ?? null,
      label: filters?.label ?? null,
      labeled: filters?.labeled ?? null,
      sort: filters?.sort ?? "id_desc",
    },
    sort: filters?.sort ?? "id_desc",
  };
}

function buildCandidatesResult(
  overrides: Partial<ReturnType<typeof useBlogLabelingCandidates>> = {},
) {
  return {
    data: buildCandidatesData(),
    isLoading: false,
    isFetching: false,
    error: null,
    refetch: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  } as unknown as ReturnType<typeof useBlogLabelingCandidates>;
}

function renderBlogLabelingPage(initialEntry = "/blog-labeling") {
  const router = createMemoryRouter(
    [{ path: "/blog-labeling", element: <BlogLabelingPage /> }],
    { initialEntries: [initialEntry] },
  );
  render(<RouterProvider router={router} />);
  return router;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedUseBlogLabelingCandidates.mockImplementation((options) =>
    buildCandidatesResult({
      data: buildCandidatesData(options.page, {
        q: options.q,
        label: options.label,
        labeled: options.labeled,
        sort: options.sort,
      }),
    }),
  );
  mockedUseCreateBlogLabelTag.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue(undefined),
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useCreateBlogLabelTag>);
  mockedUseExportBlogLabelTrainingCsv.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue("url,title,label\nhttps://alpha.example/,Alpha Blog,blog\n"),
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useExportBlogLabelTrainingCsv>);
  mockedUseReplaceBlogLinkLabels.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    variables: undefined,
    error: null,
  } as unknown as ReturnType<typeof useReplaceBlogLinkLabels>);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

test("maps url filters into the multi-tag labeling query", () => {
  renderBlogLabelingPage("/blog-labeling?page=2&label=official&labeled=true");

  expect(mockedUseBlogLabelingCandidates).toHaveBeenLastCalledWith({
    page: 2,
    pageSize: 50,
    q: null,
    label: "official",
    labeled: true,
    sort: "id_desc",
  });
  expect(screen.getByRole("heading", { name: "博客人工标注台" })).toBeInTheDocument();
  expect(screen.getAllByText("blog").length).toBeGreaterThan(0);
  expect(screen.getAllByText("official").length).toBeGreaterThan(0);
});

test("debounces filter changes and resets paging in the url", async () => {
  vi.useFakeTimers();
  const router = renderBlogLabelingPage("/blog-labeling?page=3&label=blog");

  const searchInput = screen.getByRole("searchbox", { name: "通用搜索" });
  fireEvent.change(searchInput, { target: { value: "gamma" } });

  expect(router.state.location.search).toBe("?page=3&label=blog");

  await act(async () => {
    await vi.advanceTimersByTimeAsync(300);
  });

  expect(router.state.location.search).toBe("?q=gamma&label=blog");
  expect(mockedUseBlogLabelingCandidates).toHaveBeenLastCalledWith({
    page: 1,
    pageSize: 50,
    q: "gamma",
    label: "blog",
    labeled: null,
    sort: "id_desc",
  });
});

test("creates tag types from the frontend form", async () => {
  const mutateAsync = vi.fn().mockResolvedValue(undefined);
  mockedUseCreateBlogLabelTag.mockReturnValue({
    mutateAsync,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useCreateBlogLabelTag>);
  const user = userEvent.setup();

  renderBlogLabelingPage();
  await user.type(screen.getByRole("textbox", { name: "新标签名" }), "government");
  await user.click(screen.getByRole("button", { name: "新建标签" }));

  await waitFor(() => {
    expect(mutateAsync).toHaveBeenCalledWith({ name: "government" });
  });
});

test("replaces a blog's tag set when toggling one label", async () => {
  const mutate = vi.fn();
  mockedUseReplaceBlogLinkLabels.mockReturnValue({
    mutate,
    isPending: false,
    variables: undefined,
    error: null,
  } as unknown as ReturnType<typeof useReplaceBlogLinkLabels>);
  const user = userEvent.setup();

  renderBlogLabelingPage();
  await user.click(screen.getByRole("button", { name: "标记 blog" }));

  await waitFor(() => {
    expect(mutate).toHaveBeenCalledWith({ blogId: 1, tagIds: [10] });
  });
});

test("exports the labeled dataset as training csv", async () => {
  const mutateAsync = vi.fn().mockResolvedValue("url,title,label\nhttps://alpha.example/,Alpha Blog,blog\n");
  mockedUseExportBlogLabelTrainingCsv.mockReturnValue({
    mutateAsync,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useExportBlogLabelTrainingCsv>);
  const user = userEvent.setup();
  const createObjectUrl = vi.fn(() => "blob:training-csv");
  const revokeObjectUrl = vi.fn();
  const originalCreateObjectURL = URL.createObjectURL;
  const originalRevokeObjectURL = URL.revokeObjectURL;
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    writable: true,
    value: createObjectUrl,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    writable: true,
    value: revokeObjectUrl,
  });
  const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

  try {
    renderBlogLabelingPage();
    await user.click(screen.getByRole("button", { name: "导出训练 CSV" }));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledTimes(1);
    });
    expect(createObjectUrl).toHaveBeenCalledTimes(1);
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(revokeObjectUrl).toHaveBeenCalledTimes(1);
  } finally {
    clickSpy.mockRestore();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: originalCreateObjectURL,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      writable: true,
      value: originalRevokeObjectURL,
    });
  }
});
