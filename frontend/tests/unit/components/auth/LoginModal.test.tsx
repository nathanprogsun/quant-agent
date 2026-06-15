// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { LoginModal } from "@/components/auth/LoginModal";
import { AuthProvider } from "@/core/auth/AuthProvider";
import { LoginModalProvider } from "@/contexts/LoginModalContext";

function renderLoginModal(defaultOpen = true) {
  return render(
    <AuthProvider initialUser={null}>
      <LoginModalProvider defaultOpen={defaultOpen}>
        <LoginModal />
      </LoginModalProvider>
    </AuthProvider>,
  );
}

describe("LoginModal", () => {
  test("renders when defaultOpen is true", () => {
    renderLoginModal(true);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("登录 Quant Agent")).toBeInTheDocument();
  });

  test("does not render when defaultOpen is false", () => {
    renderLoginModal(false);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("closes and syncs auth after successful login", async () => {
    const mockUser = {
      id: "123e4567-e89b-12d3-a456-426614174000",
      email: "test@example.com",
      username: "testuser",
      full_name: "Test User",
      is_active: true,
      is_superuser: false,
    };

    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes("/auth/login")) {
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      }
      if (url.includes("/auth/me")) {
        return new Response(
          JSON.stringify({ status: "authenticated", user: mockUser }),
          { status: 200 },
        );
      }
      return new Response(null, { status: 404 });
    });

    renderLoginModal(true);

    await userEvent.type(screen.getByLabelText("邮箱"), "test@example.com");
    await userEvent.type(screen.getByLabelText("密码"), "password123");
    await userEvent.click(screen.getByRole("button", { name: "登录" }));

    await vi.waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });
});
