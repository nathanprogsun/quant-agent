/**
 * Shared mock helpers for E2E tests.
 *
 * Intercepts all API endpoints so tests can run without a real backend.
 * - Auth endpoints: `/api/v1/auth/...` (Next.js API routes)
 * - Thread/LangGraph endpoints: `/api/threads/...` (LangGraph SDK calls)
 */

import type { Page, Route } from "@playwright/test";

// ── Constants ───────────────────────────────────────────────────────────────

export const MOCK_USER = {
  id: "00000000-0000-0000-0000-000000000001",
  email: "test@example.com",
  username: "testuser",
  full_name: "Test User",
  is_active: true,
  is_superuser: true,
};

export const MOCK_THREAD_ID = "00000000-0000-0000-0000-000000000001";
export const MOCK_THREAD_ID_2 = "00000000-0000-0000-0000-000000000002";
export const MOCK_RUN_ID = "00000000-0000-0000-0000-000000000099";

// ── Types ───────────────────────────────────────────────────────────────────

export type MockThread = {
  thread_id: string;
  title?: string;
  updated_at?: string;
  messages?: unknown[];
};

export type MockAPIOptions = {
  threads?: MockThread[];
  setupStatus?: { needs_setup: boolean };
};

// ── Auth API Mocks ──────────────────────────────────────────────────────────

/**
 * Mock authentication-related API endpoints.
 * These are Next.js API routes at /api/v1/auth/...
 */
export function mockAuthAPI(page: Page, options?: MockAPIOptions) {
  // GET /api/v1/auth/me — AuthProvider refresh
  void page.route("**/api/v1/auth/me", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "authenticated", user: MOCK_USER }),
      });
    }
    return route.fallback();
  });

  // POST /api/v1/auth/login
  void page.route("**/api/v1/auth/login", (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true }),
      });
    }
    return route.fallback();
  });

  // POST /api/v1/auth/register
  void page.route("**/api/v1/auth/register", (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true }),
      });
    }
    return route.fallback();
  });

  // POST /api/v1/auth/logout
  void page.route("**/api/v1/auth/logout", (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true }),
      });
    }
    return route.fallback();
  });

  // GET /api/v1/auth/setup-status
  void page.route("**/api/v1/auth/setup-status", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          options?.setupStatus ?? { needs_setup: false },
        ),
      });
    }
    return route.fallback();
  });

  // POST /api/v1/auth/initialize
  void page.route("**/api/v1/auth/initialize", (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true }),
      });
    }
    return route.fallback();
  });
}

// ── Thread API Mocks ────────────────────────────────────────────────────────

/**
 * Mock thread CRUD API endpoints.
 * LangGraph SDK calls /api/threads/... (no v1 prefix).
 * Browser-side hooks call /api/v1/threads/... (Next.js API routes).
 */
export function mockThreadAPI(page: Page, options?: MockAPIOptions) {
  const threads = options?.threads ?? [];

  // ── LangGraph SDK endpoints (/api/threads/...) ──

  // GET /api/threads/search — useThreads list (via threadApi.listThreads)
  void page.route("**/api/threads/search", (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          threads.map((t) => ({
            thread_id: t.thread_id,
            created_at: "2025-01-01T00:00:00Z",
            updated_at: t.updated_at ?? "2025-01-01T00:00:00Z",
            metadata: {},
            status: "idle",
            values: { title: t.title ?? "Untitled" },
          })),
        ),
      });
    }
    return route.fallback();
  });

  // POST /api/threads — create thread
  void page.route("**/api/threads", (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          thread_id: MOCK_THREAD_ID,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          metadata: {},
          status: "idle",
          values: {},
        }),
      });
    }

    // GET /api/threads — list (fallback for search)
    if (route.request().method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          threads.map((t) => ({
            thread_id: t.thread_id,
            created_at: "2025-01-01T00:00:00Z",
            updated_at: t.updated_at ?? "2025-01-01T00:00:00Z",
            metadata: {},
            status: "idle",
            values: { title: t.title ?? "Untitled" },
          })),
        ),
      });
    }

    return route.fallback();
  });

  // PATCH/DELETE/GET /api/threads/:id
  void page.route("**/api/threads/*", (route) => {
    const url = route.request().url();
    const method = route.request().method();

    // Avoid matching sub-paths like /api/threads/:id/history
    const pathPart = url.split("/api/threads/")[1] ?? "";
    const threadId = pathPart.split("/")[0]?.split("?")[0];

    // Skip if this is a sub-path (has more segments)
    if (pathPart.includes("/")) {
      return route.fallback();
    }

    if (method === "GET") {
      const thread = threads.find((t) => t.thread_id === threadId);
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          thread_id: threadId,
          created_at: "2025-01-01T00:00:00Z",
          updated_at: thread?.updated_at ?? "2025-01-01T00:00:00Z",
          metadata: {},
          status: "idle",
          values: { title: thread?.title ?? "Untitled" },
        }),
      });
    }

    if (method === "PATCH") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ thread_id: threadId }),
      });
    }

    if (method === "DELETE") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true }),
      });
    }

    return route.fallback();
  });

  // GET /api/threads/:id/history — useStream state history
  void page.route("**/api/threads/*/history", (route) => {
    const url = route.request().url();
    const matchingThread = threads.find((t) => url.includes(t.thread_id));

    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        matchingThread
          ? [
              {
                values: {
                  title: matchingThread.title ?? "Untitled",
                  messages: matchingThread.messages ?? [],
                },
                next: [],
                metadata: {},
                created_at: "2025-01-01T00:00:00Z",
                parent_config: null,
              },
            ]
          : [],
      ),
    });
  });

  // GET /api/threads/:id/state — useStream getState
  void page.route("**/api/threads/*/state", (route) => {
    if (route.request().method() === "GET") {
      const url = route.request().url();
      const matchingThread = threads.find((t) => url.includes(t.thread_id));
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          values: {
            title: matchingThread?.title ?? "Untitled",
            messages: matchingThread?.messages ?? [],
          },
          next: [],
          metadata: {},
          created_at: "2025-01-01T00:00:00Z",
        }),
      });
    }
    return route.fallback();
  });

  // POST /api/threads/:id/runs/stream — SSE streaming
  void page.route("**/api/threads/*/runs/stream", handleRunStream);

  // GET /api/threads/:id/runs — runs list (useStream may call this)
  void page.route(/\/api\/threads\/[^/]+\/runs(\?|$)/, (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    }
    return route.fallback();
  });

  // ── Next.js API routes (/api/v1/threads/...) ──
  // These are called by the browser-side hooks (useThreads, etc.)

  // GET /api/v1/threads — list (returns Thread[] with `id` field)
  void page.route("**/api/v1/threads", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          threads.map((t) => ({
            id: t.thread_id,
            user_id: "user-1",
            title: t.title ?? "Untitled",
            created_at: "2025-01-01T00:00:00Z",
            updated_at: t.updated_at ?? "2025-01-01T00:00:00Z",
          })),
        ),
      });
    }

    // POST /api/v1/threads — create
    if (route.request().method() === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: MOCK_THREAD_ID,
          user_id: "user-1",
          title: "New Chat",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }),
      });
    }

    return route.fallback();
  });

  // GET/PATCH/DELETE /api/v1/threads/:id
  void page.route("**/api/v1/threads/*", (route) => {
    const url = route.request().url();
    const method = route.request().method();
    const pathPart = url.split("/api/v1/threads/")[1] ?? "";
    const threadId = pathPart.split("/")[0]?.split("?")[0];

    if (method === "GET") {
      const thread = threads.find((t) => t.thread_id === threadId);
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: threadId,
          user_id: "user-1",
          title: thread?.title ?? "Untitled",
          created_at: "2025-01-01T00:00:00Z",
          updated_at: thread?.updated_at ?? "2025-01-01T00:00:00Z",
        }),
      });
    }

    if (method === "PATCH") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: threadId,
          user_id: "user-1",
          title: "Updated",
          created_at: "2025-01-01T00:00:00Z",
          updated_at: new Date().toISOString(),
        }),
      });
    }

    if (method === "DELETE") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true }),
      });
    }

    return route.fallback();
  });
}

// ── SSE Stream Handler ──────────────────────────────────────────────────────

/**
 * Build a minimal SSE stream that the LangGraph SDK can parse.
 * Returns a single AI message: "Quant Agent 分析完成！".
 */
export function handleRunStream(route: Route) {
  const events = [
    {
      event: "metadata",
      data: { run_id: MOCK_RUN_ID, thread_id: MOCK_THREAD_ID },
    },
    {
      event: "values",
      data: {
        messages: [
          {
            type: "human",
            id: "msg-human-1",
            content: [{ type: "text", text: "Hello" }],
          },
          {
            type: "ai",
            id: "msg-ai-1",
            content: "Quant Agent 分析完成！",
          },
        ],
      },
    },
    { event: "end", data: {} },
  ];

  const body = events
    .map((e) => `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`)
    .join("");

  return route.fulfill({
    status: 200,
    contentType: "text/event-stream",
    body,
  });
}

/**
 * Build an SSE stream with tool call messages.
 */
export function handleRunStreamWithTools(route: Route) {
  const events = [
    {
      event: "metadata",
      data: { run_id: MOCK_RUN_ID, thread_id: MOCK_THREAD_ID },
    },
    {
      event: "values",
      data: {
        messages: [
          {
            type: "human",
            id: "msg-human-1",
            content: [{ type: "text", text: "分析茅台股票" }],
          },
          {
            type: "ai",
            id: "msg-ai-1",
            content: "",
            tool_calls: [
              {
                id: "call-1",
                name: "query_stock_data",
                args: '{"symbol": "600519"}',
              },
            ],
          },
          {
            type: "tool",
            id: "msg-tool-1",
            tool_call_id: "call-1",
            content: '{"price": 1800, "volume": 12345}',
          },
          {
            type: "ai",
            id: "msg-ai-2",
            content: "茅台当前价格 1800 元，成交量 12345 手。",
          },
        ],
      },
    },
    { event: "end", data: {} },
  ];

  const body = events
    .map((e) => `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`)
    .join("");

  return route.fulfill({
    status: 200,
    contentType: "text/event-stream",
    body,
  });
}

// ── Convenience ─────────────────────────────────────────────────────────────

/**
 * Set the e2e_bypass_auth cookie so SSR auth guard returns mock user.
 * Call this before page.goto() for workspace pages.
 */
export async function enableAuthBypass(page: Page) {
  await page.context().addCookies([
    {
      name: "e2e_bypass_auth",
      value: "1",
      domain: "localhost",
      path: "/",
    },
  ]);
}

/**
 * Mock all API endpoints at once.
 */
export function mockAllAPIs(page: Page, options?: MockAPIOptions) {
  mockAuthAPI(page, options);
  mockThreadAPI(page, options);
}
