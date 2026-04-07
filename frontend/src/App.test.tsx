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

  expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /统计总览/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /发现博客/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /搜索发现/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /当前处理/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /控制台/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /项目介绍/i })).toBeInTheDocument();
});
