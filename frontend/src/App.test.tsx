import { expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { AppLayout } from "./shell/AppLayout";

test("renders primary navigation entries", () => {
  const queryClient = new QueryClient();
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AppLayout />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(screen.getByText("统计总览")).toBeInTheDocument();
  expect(screen.getByText("发现博客")).toBeInTheDocument();
  expect(screen.getByText("搜索发现")).toBeInTheDocument();
  expect(screen.getByText("当前处理")).toBeInTheDocument();
  expect(screen.getByText("控制台")).toBeInTheDocument();
  expect(screen.getByText("项目介绍")).toBeInTheDocument();
});
