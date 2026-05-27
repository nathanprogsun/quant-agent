import { cookies } from "next/headers";

import type { AuthResult, User } from "./types";
import { userSchema } from "./types";

const AUTH_ME_ENDPOINT = "/api/v1/auth/me";
const SSR_TIMEOUT_MS = 5_000;

const E2E_MOCK_USER: User = {
  id: "00000000-0000-0000-0000-000000000001",
  email: "test@example.com",
  username: "testuser",
  full_name: "Test User",
  is_active: true,
  is_superuser: true,
};

/**
 * Server-side auth check for use in Server Components and layouts.
 * Reads the HttpOnly session cookie and validates it against the backend.
 */
export async function getServerSideUser(): Promise<AuthResult> {
  const cookieStore = await cookies();

  // E2E bypass: when the e2e_bypass_auth cookie is set, return mock user.
  // Workspace tests set this cookie before navigating; auth tests don't.
  if (cookieStore.get("e2e_bypass_auth")?.value === "1") {
    return { status: "authenticated", user: E2E_MOCK_USER };
  }

  const sessionCookie = cookieStore.get("access_token");

  // Debug: log all cookies received in SSR
  const allCookies = cookieStore.getAll();
  console.log("[SSR] cookies:", allCookies.map((c) => `${c.name}=${c.value.substring(0, 20)}...`));
  console.log("[SSR] access_token:", sessionCookie?.value ? `${sessionCookie.value.substring(0, 20)}...` : "MISSING");

  if (!sessionCookie?.value) {
    try {
      const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), SSR_TIMEOUT_MS);

      const statusResponse = await fetch(
        `${backendUrl}/api/v1/auth/setup-status`,
        {
          signal: controller.signal,
          cache: "no-store",
        }
      );

      clearTimeout(timeoutId);

      if (statusResponse.ok) {
        const statusData = await statusResponse.json();
        if (statusData.needs_setup) {
          return { status: "needs_setup" };
        }
      }
    } catch {
      // Fall through to unauthenticated if status check fails
    }
    return { status: "unauthenticated" };
  }


  try {
    const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), SSR_TIMEOUT_MS);

    const response = await fetch(`${backendUrl}${AUTH_ME_ENDPOINT}`, {
      headers: {
        Cookie: `access_token=${sessionCookie.value}`,
      },
      signal: controller.signal,
      cache: "no-store",
    });

    clearTimeout(timeoutId);

    if (response.status === 401) {
      return { status: "unauthenticated" };
    }

    if (!response.ok) {
      console.error(`Auth check failed: ${response.status}`);
      return { status: "gateway_unavailable" };
    }

    const data = await response.json();
    const parsed = userSchema.safeParse(data);

    if (!parsed.success) {
      console.error("Invalid user data from backend:", parsed.error);
      return { status: "config_error", message: "Invalid user data format" };
    }

    return { status: "authenticated", user: parsed.data };
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      console.error("Auth check timed out");
      return { status: "gateway_unavailable" };
    }
    console.error("Auth check error:", error);
    return { status: "gateway_unavailable" };
  }
}
