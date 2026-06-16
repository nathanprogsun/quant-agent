// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/core/auth/AuthProvider", () => ({
  useAuth: () => ({ isAuthenticated: false }),
}));

vi.mock("@/contexts/LoginModalContext", () => ({
  useLoginModal: () => ({ openLoginModal: vi.fn() }),
}));

vi.mock("@/hooks/useThreads", () => ({
  useCreateThread: () => ({ mutate: vi.fn(), isPending: false }),
}));

import { WorkspaceHome } from "@/components/workspace/WorkspaceHome";

describe("WorkspaceHome", () => {
  test("renders title with text-3xl class", () => {
    render(<WorkspaceHome />);
    const title = screen.getByText("JoinQuant人工智能投研平台");
    expect(title).toHaveClass("text-3xl");
  });

  test("renders subtitle", () => {
    render(<WorkspaceHome />);
    expect(screen.getByText("智能投研 Quant Agent")).toBeInTheDocument();
  });
});
