// @vitest-environment jsdom
import { renderHook, act } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { useStrategyWorkspace } from "@/hooks/useStrategyWorkspace";

describe("useStrategyWorkspace", () => {
  test("workspace panel stays closed until explicitly opened", () => {
    const { result } = renderHook(() => useStrategyWorkspace());

    expect(result.current.isOpen).toBe(false);
  });

  test("openWorkspace reveals the panel on code tab", () => {
    const { result } = renderHook(() => useStrategyWorkspace());

    act(() => {
      result.current.openWorkspace();
    });

    expect(result.current.isOpen).toBe(true);
    expect(result.current.activeTab).toBe("code");
  });

  test("closeWorkspace hides the panel", () => {
    const { result } = renderHook(() => useStrategyWorkspace());

    act(() => {
      result.current.openWorkspace();
      result.current.closeWorkspace();
    });

    expect(result.current.isOpen).toBe(false);
  });
});
