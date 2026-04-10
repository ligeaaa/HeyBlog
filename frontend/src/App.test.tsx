import type { ReactNode } from "react";
import { expect, test } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { AdminLayout } from "./shell/AdminLayout";
import { PublicLayout } from "./shell/PublicLayout";

function renderWithProviders(node: ReactNode) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

test("renders only public navigation entries in public layout", () => {
  cleanup();
  renderWithProviders(<PublicLayout />);

  const nav = screen.getByRole("navigation", { name: "Public navigation" });
  expect(nav).toBeInTheDocument();
  expect(within(nav).getByRole("link", { name: /统计总览/i })).toBeInTheDocument();
  expect(within(nav).getByRole("link", { name: /发现博客/i })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /控制台/i })).not.toBeInTheDocument();
});

test("renders admin navigation and auth gate in admin layout", () => {
  cleanup();
  renderWithProviders(<AdminLayout />);

  const nav = screen.getByRole("navigation", { name: "Admin navigation" });
  expect(nav).toBeInTheDocument();
  expect(within(nav).getByRole("link", { name: /控制台/i })).toBeInTheDocument();
  expect(screen.getByLabelText(/Admin token/i)).toBeInTheDocument();
  expect(within(nav).queryByRole("link", { name: /发现博客/i })).not.toBeInTheDocument();
});
