import { describe, expect, test, vi } from "vitest";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { useBlogCatalog } from "./hooks";

vi.mock("@tanstack/react-query", () => ({
  useMutation: vi.fn(),
  useQuery: vi.fn(),
  useQueryClient: vi.fn(),
}));

vi.mock("./api", () => ({
  api: {
    blogCatalog: vi.fn(),
  },
}));

describe("useBlogCatalog", () => {
  test("uses a non-polling query configuration", async () => {
    vi.mocked(useQuery).mockReturnValue({} as never);
    vi.mocked(api.blogCatalog).mockResolvedValue({} as never);

    useBlogCatalog({
      page: 2,
      site: "alpha",
      status: "FINISHED",
    });

    expect(useQuery).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: [
          "blog-catalog",
          {
            page: 2,
            pageSize: 50,
            q: null,
            site: "alpha",
            url: null,
            status: "FINISHED",
          },
        ],
        enabled: true,
        staleTime: 30000,
        refetchInterval: false,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
      }),
    );

    const queryConfig = vi.mocked(useQuery).mock.calls[0][0] as unknown as {
      queryFn: (context?: unknown) => Promise<unknown>;
    };
    await queryConfig.queryFn({} as never);

    expect(api.blogCatalog).toHaveBeenCalledWith({
      page: 2,
      pageSize: 50,
      q: null,
      site: "alpha",
      url: null,
      status: "FINISHED",
    });
  });
});
