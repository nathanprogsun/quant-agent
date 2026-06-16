// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { StrategyCodeCard } from "@/components/workspace/StrategyCodeCard";

describe("StrategyCodeCard", () => {
  test("renders strategy name", () => {
    render(<StrategyCodeCard strategyName="小市值策略" />);

    expect(screen.getByText("小市值策略")).toBeInTheDocument();
    expect(screen.getByText("点击查看")).toBeInTheDocument();
  });

  test("calls onOpenCode when clicked", async () => {
    const onOpenCode = vi.fn();
    render(
      <StrategyCodeCard strategyName="测试策略" onOpenCode={onOpenCode} />,
    );

    await userEvent.click(screen.getByRole("button"));

    expect(onOpenCode).toHaveBeenCalledTimes(1);
  });
});
