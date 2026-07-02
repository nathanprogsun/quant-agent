import { expect, test, type Page } from "@playwright/test";

const TEST_PASSWORD = "TestPassword123!";
const TEST_FULL_NAME = "E2E User";

function uniqueEmail(): string {
  return `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
}

async function loginViaUi(page: Page) {
  await page.goto("/login");

  await page.getByRole("button", { name: "注册" }).click();

  await page.getByLabel(/姓名/).fill(TEST_FULL_NAME);
  await page.getByLabel(/邮箱/).fill(uniqueEmail());
  await page.getByLabel(/密码/).fill(TEST_PASSWORD);
  await page.getByRole("button", { name: "注册" }).click();

  await page.waitForURL("**/workspace**", { timeout: 30_000 });
}

function buildMockChatStream(threadId: string, runId: string): string {
  return [
    `event: metadata\ndata: ${JSON.stringify({ thread_id: threadId, run_id: runId })}\n\n`,
    `event: messages\ndata: ${JSON.stringify([
      { content: "Hello from mock assistant", type: "ai", id: "ai-1" },
      { node: "agent" },
    ])}\n\n`,
    `event: values\ndata: ${JSON.stringify({
      messages: [
        { type: "human", content: "Hello quant agent" },
        { type: "ai", content: "Hello from mock assistant" },
      ],
    })}\n\n`,
    `event: end\ndata: null\n\n`,
  ].join("");
}

test.describe("TC2: Thread CRUD and sidebar", () => {
  test("new user sidebar shows empty state", async ({ page }) => {
    await page.route("**/api/v1/threads", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          status: 200,
          body: JSON.stringify({ threads: [] }),
        });
      } else {
        await route.fulfill({ status: 200, body: JSON.stringify({ id: "mock-thread-1", title: "", created_at: new Date().toISOString() }) });
      }
    });

    await loginViaUi(page);

    await page.getByRole("button", { name: "切换侧栏" }).click();
    await expect(page.getByText("暂无对话")).toBeVisible();
  });

  test("create thread and verify it appears in sidebar", async ({ page }) => {
    const mockThreadId = `mock-thread-${Date.now()}`;
    const mockThread = {
      id: mockThreadId,
      title: "Hello quant agent",
      created_at: new Date().toISOString(),
    };
    const mockRunId = "00000000-0000-4000-8000-000000000002";

    await page.route("**/api/v1/threads", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          status: 200,
          body: JSON.stringify({ threads: [mockThread] }),
        });
      } else if (route.request().method() === "POST") {
        await route.fulfill({
          status: 201,
          body: JSON.stringify(mockThread),
        });
      } else {
        await route.fulfill({ status: 405 });
      }
    });

    await page.route(`**/api/v1/threads/${mockThreadId}`, async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          status: 200,
          body: JSON.stringify(mockThread),
        });
      } else {
        await route.fulfill({ status: 405 });
      }
    });

    await page.route("**/api/threads/**/runs/stream", async (route) => {
      await route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
        body: buildMockChatStream(mockThreadId, mockRunId),
      });
    });

    await loginViaUi(page);

    await page.getByPlaceholder(/请输入您的策略想法/).fill("Hello quant agent");
    await page.getByRole("button", { name: "发送" }).click();

    await page.waitForURL(`**/workspace/chats/${mockThreadId}`, { timeout: 30_000 });
    await expect(page.getByText("Hello from mock assistant")).toBeVisible({ timeout: 15_000 });

    await page.goto("/workspace");
    await page.waitForLoadState("networkidle");
    await page.getByRole("button", { name: "切换侧栏" }).click();

    await expect(page.getByText("Hello quant agent")).toBeVisible();
  });
});

test.describe("TC7: Settings and integration page", () => {
  test("integration page shows jqcli status", async ({ page }) => {
    await page.route("**/api/v1/backtest/auth-check", async (route) => {
      await route.fulfill({
        status: 200,
        body: JSON.stringify({ configured: true, authenticated: true, username: "jq-test" }),
      });
    });

    await loginViaUi(page);
    await page.goto("/settings/integration");

    await expect(page.getByText("集成设置")).toBeVisible();
    await expect(page.getByText("已配置")).toBeVisible();
    await expect(page.getByText("已认证")).toBeVisible();
    await expect(page.getByText("jq-test")).toBeVisible();
  });
});

test.describe("TC8: Auth boundary", () => {
  test("unauthenticated user can see workspace but cannot send messages", async ({ page }) => {
    await page.goto("/workspace");

    await expect(page.getByText(/JoinQuant|人工智能投研平台/)).toBeVisible();

    await expect(page.getByPlaceholder(/请输入您的策略想法/)).toBeVisible();

    await page.getByPlaceholder(/请输入您的策略想法/).fill("test");
    await page.getByRole("button", { name: "发送" }).click();

    await expect(page.getByRole("button", { name: "登录" })).toBeVisible({ timeout: 5000 });
  });

  test("authenticated user sees workspace normally", async ({ page }) => {
    await loginViaUi(page);
    await page.goto("/workspace");

    await expect(page.getByText(/JoinQuant|人工智能投研平台/)).toBeVisible();
    await expect(page.getByPlaceholder(/请输入您的策略想法/)).toBeVisible();
  });
});
