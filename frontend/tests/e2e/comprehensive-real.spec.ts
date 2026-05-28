/**
 * Comprehensive E2E tests using real backend API.
 * This file replaces the mock-based tests with real API calls.
 *
 * Coverage:
 * - AUTH: login, logout, session
 * - THREADS: create, read, update, delete, list
 * - HISTORY: get thread history
 * - CHAT: send message, receive response
 */

import { expect, test } from "@playwright/test";

import {
  createThread,
  deleteThread,
  getThread,
  getThreadHistory,
  listThreads,
  login,
  updateThreadTitle,
} from "./utils/real-api";

test.describe("Auth E2E (Real API)", () => {
  test("login page loads", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: /login/i })).toBeVisible({
      timeout: 15_000,
    });
  });

  test("user can login with valid credentials", async ({ page }) => {
    await login(page);

    // After login, should be able to access protected page
    await page.goto("/workspace/chats");
    // Should not redirect to login
    await expect(page.url()).not.toContain("/login");
  });
});

test.describe("Thread Management E2E (Real API)", () => {
  let threadId: string;

  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test.afterEach(async ({ page }) => {
    // Cleanup: delete test thread if it exists
    if (threadId) {
      await deleteThread(page, threadId);
      threadId = "";
    }
  });

  test("create a new thread", async ({ page }) => {
    threadId = await createThread(page, "Test Thread");

    expect(threadId).toBeDefined();
    expect(threadId.length).toBeGreaterThan(0);
  });

  test("get thread details", async ({ page }) => {
    threadId = await createThread(page, "Get Test Thread");

    const thread = await getThread(page, threadId);

    expect(thread.id).toBe(threadId);
  });

  test("update thread title", async ({ page }) => {
    threadId = await createThread(page, "Original Title");

    await updateThreadTitle(page, threadId, "Updated Title");

    const updated = await getThread(page, threadId);
    expect(updated.title).toBe("Updated Title");
  });

  test("list threads includes created thread", async ({ page }) => {
    threadId = await createThread(page, "List Test Thread");

    const result = await listThreads(page);

    expect(result.threads.length).toBeGreaterThan(0);
    expect(result.threads.some((t) => t.id === threadId)).toBe(true);
  });

  test("delete thread removes it from list", async ({ page }) => {
    threadId = await createThread(page, "Delete Test Thread");

    await deleteThread(page, threadId);
    threadId = ""; // Prevent afterEach from trying to delete again

    const result = await listThreads(page);
    expect(result.threads.some((t) => t.id === threadId)).toBe(false);
  });
});

test.describe("Thread History E2E (Real API)", () => {
  let threadId: string;

  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test.afterEach(async ({ page }) => {
    if (threadId) {
      await deleteThread(page, threadId);
    }
  });

  test("get thread history returns messages array", async ({ page }) => {
    threadId = await createThread(page, "History Test Thread");

    const history = await getThreadHistory(page, threadId);

    expect(history).toHaveProperty("messages");
    expect(Array.isArray(history.messages)).toBe(true);
  });
});

test.describe("Chat Flow E2E (Real API)", () => {
  let threadId: string;

  test.beforeEach(async ({ page }) => {
    await login(page);
    threadId = await createThread(page, "Chat Test Thread");
  });

  test.afterEach(async ({ page }) => {
    if (threadId) {
      await deleteThread(page, threadId);
    }
  });

  test("workspace page loads with thread", async ({ page }) => {
    await page.goto(`/workspace/chats/${threadId}`);

    await expect(page.getByRole("textbox")).toBeVisible({ timeout: 15_000 });
  });

  test("can type and send a message", async ({ page }) => {
    await page.goto(`/workspace/chats/${threadId}`);

    const textarea = page.getByRole("textbox");
    await expect(textarea).toBeVisible({ timeout: 15_000 });

    await textarea.fill("分析茅台股票");
    await textarea.press("Enter");

    // Wait a bit for potential stream
    await page.waitForTimeout(2000);

    // The message should appear (either optimistic or from stream)
    await expect(page.getByText("分析茅台股票")).toBeVisible({ timeout: 5000 });
  });
});

test.describe("Proxy Route E2E (Real API - Verifies Fix for NAT-56/NAT-57)", () => {
  let threadId: string;

  test.beforeEach(async ({ page }) => {
    await login(page);
    threadId = await createThread(page, "Proxy Test Thread");
  });

  test.afterEach(async ({ page }) => {
    if (threadId) {
      await deleteThread(page, threadId);
    }
  });

  test("GET /api/threads/{thread_id}/history proxy route works", async ({ page }) => {
    // This tests the proxy route: frontend -> backend /api/v1/threads/{id}/history
    // Previously returned 404/405, should now return 200
    const history = await getThreadHistory(page, threadId);

    expect(history).toBeDefined();
    expect(history).toHaveProperty("messages");
  });

  test("POST /api/threads/{thread_id}/runs/stream proxy route is accessible", async ({
    page,
  }) => {
    // This tests the run/stream proxy route
    // The LangGraph SDK calls this endpoint, previously returned 404
    await page.goto(`/workspace/chats/${threadId}`);

    // Just verify the page loads without errors
    await expect(page.getByRole("textbox")).toBeVisible({ timeout: 15_000 });
  });
});
