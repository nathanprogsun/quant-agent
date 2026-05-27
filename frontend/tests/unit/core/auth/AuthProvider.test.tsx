// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { AuthProvider, useAuth } from "@/core/auth/AuthProvider";
import type { User } from "@/core/auth/types";

// Test component that exposes auth context
function AuthConsumer() {
  const { user, isAuthenticated, isLoading, logout, refresh } = useAuth();
  return (
    <div>
      <span data-testid="user">{user ? user.email : "null"}</span>
      <span data-testid="isAuthenticated">{String(isAuthenticated)}</span>
      <span data-testid="isLoading">{String(isLoading)}</span>
      <button onClick={logout}>Logout</button>
      <button onClick={() => void refresh()}>Refresh</button>
    </div>
  );
}

const mockUser: User = {
  id: "123e4567-e89b-12d3-a456-426614174000",
  email: "test@example.com",
  username: "testuser",
  full_name: "Test User",
  is_active: true,
  is_superuser: false,
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AuthProvider", () => {
  test("provides initial user", () => {
    render(
      <AuthProvider initialUser={mockUser}>
        <AuthConsumer />
      </AuthProvider>,
    );

    expect(screen.getByTestId("user")).toHaveTextContent("test@example.com");
    expect(screen.getByTestId("isAuthenticated")).toHaveTextContent("true");
  });

  test("provides null user when unauthenticated", () => {
    render(
      <AuthProvider initialUser={null}>
        <AuthConsumer />
      </AuthProvider>,
    );

    expect(screen.getByTestId("user")).toHaveTextContent("null");
    expect(screen.getByTestId("isAuthenticated")).toHaveTextContent("false");
  });

  test("logout clears user state", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(null, { status: 200 }),
    );

    render(
      <AuthProvider initialUser={mockUser}>
        <AuthConsumer />
      </AuthProvider>,
    );

    expect(screen.getByTestId("isAuthenticated")).toHaveTextContent("true");

    await userEvent.click(screen.getByText("Logout"));

    expect(screen.getByTestId("isAuthenticated")).toHaveTextContent("false");
    expect(screen.getByTestId("user")).toHaveTextContent("null");
  });

  test("refresh updates user from API", async () => {
    // Advance time to bypass throttle
    vi.useFakeTimers({ shouldAdvanceTime: true });

    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ status: "authenticated", user: mockUser }),
        { status: 200 },
      ),
    );

    render(
      <AuthProvider initialUser={null}>
        <AuthConsumer />
      </AuthProvider>,
    );

    expect(screen.getByTestId("isAuthenticated")).toHaveTextContent("false");

    // Advance past throttle
    vi.advanceTimersByTime(61000);

    await userEvent.click(screen.getByText("Refresh"));

    await waitFor(() => {
      expect(screen.getByTestId("isAuthenticated")).toHaveTextContent("true");
    });

    expect(screen.getByTestId("user")).toHaveTextContent("test@example.com");

    vi.useRealTimers();
  });

  test("refresh clears user on 401", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });

    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(null, { status: 401 }),
    );

    render(
      <AuthProvider initialUser={mockUser}>
        <AuthConsumer />
      </AuthProvider>,
    );

    expect(screen.getByTestId("isAuthenticated")).toHaveTextContent("true");

    vi.advanceTimersByTime(61000);

    await userEvent.click(screen.getByText("Refresh"));

    await waitFor(() => {
      expect(screen.getByTestId("isAuthenticated")).toHaveTextContent("false");
    });

    vi.useRealTimers();
  });
});

describe("useAuth hook", () => {
  test("throws when used outside AuthProvider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});

    expect(() => render(<AuthConsumer />)).toThrow(
      "useAuth must be used within an AuthProvider",
    );

    spy.mockRestore();
  });
});
