// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { WorkspaceTopBar } from "@/components/workspace/WorkspaceTopBar";

describe("WorkspaceTopBar", () => {
  test("renders brand name and subtitle", () => {
    render(<WorkspaceTopBar />);
    expect(screen.getByText("QuantAgent")).toBeInTheDocument();
    expect(screen.getByText("智能投研 Quant Agent")).toBeInTheDocument();
  });

  test("logo container is circular (rounded-full)", () => {
    render(<WorkspaceTopBar />);
    const logo = screen.getByText("Q");
    expect(logo.closest("div")).toHaveClass("rounded-full");
  });
});
