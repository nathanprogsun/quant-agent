import { expect, test, type Page } from "@playwright/test";

const TEST_PASSWORD = "TestPassword123!";

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

async function loginViaUi(page: Page) {
  const testEmail = `e2e-${Date.now()}@example.com`;

  await page.goto("/setup");

  if (await page.getByRole("heading", { name: "System Setup" }).isVisible()) {
    await page.getByLabel("Full Name").fill("E2E User");
    await page.getByLabel("Email").fill(testEmail);
    await page.getByLabel("Password").fill(TEST_PASSWORD);
    await page.getByRole("button", { name: "Initialize System" }).click();
  } else {
    await page.getByRole("button", { name: "Register" }).click();
    await page.getByLabel("Full Name").fill("E2E User");
    await page.getByLabel("Email").fill(testEmail);
    await page.getByLabel("Password").fill(TEST_PASSWORD);
    await page.getByRole("button", { name: "Create Account" }).click();
  }

  await page.waitForURL("**/workspace**", { timeout: 30_000 });
}

test("login, new chat, send message, assistant visible", async ({ page }) => {
  await page.route("**/api/threads/**/runs/stream", async (route) => {
    const url = route.request().url();
    const threadMatch = url.match(/\/api\/threads\/([^/]+)\/runs\/stream/);
    const threadId = threadMatch?.[1] ?? "mock-thread-id";
    const runId = "00000000-0000-4000-8000-000000000001";

    await route.fulfill({
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "Content-Location": `/api/threads/${threadId}/runs/${runId}`,
      },
      body: buildMockChatStream(threadId, runId),
    });
  });

  await loginViaUi(page);

  await page.goto("/workspace/chats/new");
  await expect(page.getByPlaceholder("Type a message...")).toBeVisible();

  await page.getByPlaceholder("Type a message...").fill("Hello quant agent");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByText("Hello from mock assistant")).toBeVisible({
    timeout: 15_000,
  });
});
