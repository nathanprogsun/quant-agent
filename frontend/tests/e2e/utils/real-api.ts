/**
 * Real API helpers for E2E tests.
 * These make actual HTTP requests to the backend, not mocks.
 */

import type { Page } from "@playwright/test";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export const TEST_USER = {
  email: "e2e-test@example.com",
  password: "TestPassword123!",
  full_name: "E2E Test User",
};

/**
 * Login via API and set the session cookie.
 * Call this before page.goto() for workspace pages.
 */
export async function login(page: Page): Promise<void> {
  const response = await page.request.post(`${BACKEND_URL}/api/v1/auth/login`, {
    data: {
      email: TEST_USER.email,
      password: TEST_USER.password,
    },
  });

  if (!response.ok()) {
    throw new Error(`Login failed: ${response.status()} ${await response.text()}`);
  }

  // Extract session cookie from response
  const setCookieHeader = response.headers()["set-cookie"];
  if (setCookieHeader) {
    // Parse and set cookie in browser context
    const cookieParts = setCookieHeader.split(";")[0].split("=");
    if (cookieParts.length === 2) {
      await page.context().addCookies([
        {
          name: cookieParts[0],
          value: cookieParts[1],
          domain: "localhost",
          path: "/",
        },
      ]);
    }
  }
}

/**
 * Check if user is authenticated by calling /api/v1/auth/me
 */
export async function isAuthenticated(page: Page): Promise<boolean> {
  const response = await page.request.get(`${BACKEND_URL}/api/v1/auth/me`, {
    headers: {
      Cookie: page.context().cookies().then((cookies) =>
        cookies.map((c) => `${c.name}=${c.value}`).join("; ")
      ) as unknown as string,
    },
  });
  return response.ok();
}

/**
 * Create a new thread via API and return the thread_id
 */
export async function createThread(page: Page, title?: string): Promise<string> {
  const response = await page.request.post(`${BACKEND_URL}/api/v1/threads`, {
    data: title ? { title } : {},
  });

  if (!response.ok()) {
    throw new Error(`Create thread failed: ${response.status()} ${await response.text()}`);
  }

  const data = await response.json();
  return data.id;
}

/**
 * Get thread history
 */
export async function getThreadHistory(
  page: Page,
  threadId: string
): Promise<{ messages: unknown[] }> {
  const response = await page.request.get(
    `${BACKEND_URL}/api/v1/threads/${threadId}/history`
  );

  if (!response.ok()) {
    throw new Error(`Get history failed: ${response.status()}`);
  }

  return response.json();
}

/**
 * Get thread details
 */
export async function getThread(
  page: Page,
  threadId: string
): Promise<{ id: string; title?: string }> {
  const response = await page.request.get(
    `${BACKEND_URL}/api/v1/threads/${threadId}`
  );

  if (!response.ok()) {
    throw new Error(`Get thread failed: ${response.status()}`);
  }

  return response.json();
}

/**
 * Update thread title
 */
export async function updateThreadTitle(
  page: Page,
  threadId: string,
  title: string
): Promise<void> {
  const response = await page.request.patch(
    `${BACKEND_URL}/api/v1/threads/${threadId}`,
    {
      data: { title },
    }
  );

  if (!response.ok()) {
    throw new Error(`Update thread failed: ${response.status()}`);
  }
}

/**
 * Delete a thread
 */
export async function deleteThread(page: Page, threadId: string): Promise<void> {
  const response = await page.request.delete(
    `${BACKEND_URL}/api/v1/threads/${threadId}`
  );

  if (!response.ok()) {
    throw new Error(`Delete thread failed: ${response.status()}`);
  }
}

/**
 * List all threads
 */
export async function listThreads(
  page: Page
): Promise<{ threads: Array<{ id: string; title?: string }> }> {
  const response = await page.request.get(`${BACKEND_URL}/api/v1/threads`);

  if (!response.ok()) {
    throw new Error(`List threads failed: ${response.status()}`);
  }

  return response.json();
}
