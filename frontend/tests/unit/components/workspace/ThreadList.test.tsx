// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

vi.mock("@/core/auth/AuthProvider", () => ({
  useAuth: () => ({ isAuthenticated: true, user: null }),
}));

vi.mock("@/hooks/useThreads", () => ({
  useThreads: () => ({
    data: [
      { id: "t-today", title: "今天对话", created_at: new Date(Date.now() - 1 * 60 * 60 * 1000).toISOString() },
      { id: "t-yest", title: "昨天对话", created_at: new Date(Date.now() - 26 * 60 * 60 * 1000).toISOString() },
      { id: "t-30", title: "30天内对话", created_at: new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString() },
      { id: "t-old", title: "更早对话", created_at: new Date(Date.now() - 60 * 24 * 60 * 60 * 1000).toISOString() },
    ],
    isLoading: false,
  }),
  useDeleteThread: () => ({ mutate: vi.fn() }),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/workspace",
}));

import { ThreadList } from "@/components/workspace/ThreadList";

describe("ThreadList time groups", () => {
  test("renders 昨天 group for yesterday-created thread", () => {
    render(<ThreadList showHistory />);
    expect(screen.getByText("昨天")).toBeInTheDocument();
    expect(screen.getByText("昨天对话")).toBeInTheDocument();
  });

  test("does not render 今天 group", () => {
    render(<ThreadList showHistory />);
    expect(screen.queryByText("今天")).not.toBeInTheDocument();
  });

  test("renders 30天内 group", () => {
    render(<ThreadList showHistory />);
    expect(screen.getByText("30天内")).toBeInTheDocument();
    expect(screen.getByText("30天内对话")).toBeInTheDocument();
  });

  test("renders 更早 group", () => {
    render(<ThreadList showHistory />);
    expect(screen.getByText("更早")).toBeInTheDocument();
    expect(screen.getByText("更早对话")).toBeInTheDocument();
  });

  test("today's threads appear in 昨天 group", () => {
    render(<ThreadList showHistory />);
    expect(screen.getByText("今天对话")).toBeInTheDocument();
    // 今天对话 is in the 昨天 section (since 昨天 = past 24h)
    const yesterdayHeader = screen.getByText("昨天");
    const yesterdayGroup = yesterdayHeader.parentElement;
    expect(yesterdayGroup).toContainElement(screen.getByText("今天对话"));
  });
});
