import { beforeEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("react-force-graph-2d", () => ({
  default: () => <div data-testid="fake-force-graph" />,
}));

import App from "./App";

beforeEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("renders the example-aligned graph explorer and opens the fake submit dialog", async () => {
  render(<App />);

  await waitFor(() => {
    expect(screen.getByRole("heading", { name: /博客关系网络可视化/i })).toBeInTheDocument();
  });

  expect(screen.getByTestId("fake-force-graph")).toBeInTheDocument();
  expect(screen.getByText(/当前阶段先按 `frontend_example` 的 UI 结构推进/i)).toBeInTheDocument();
  expect(screen.getByText("6")).toBeInTheDocument();
  expect(screen.getByText("10")).toBeInTheDocument();

  fireEvent.change(screen.getByPlaceholderText(/输入博客URL进行搜索/i), {
    target: { value: "https://missing.example" },
  });
  fireEvent.click(screen.getByRole("button", { name: /搜索博客 URL/i }));

  await waitFor(() => {
    expect(screen.getByRole("heading", { name: /博客未找到/i })).toBeInTheDocument();
  });
});
