import { expect, test } from "@playwright/test";

import {
  enableAuthBypass,
  handleRunStreamWithTools,
  mockAllAPIs,
  MOCK_THREAD_ID,
} from "./utils/mock-api";

test.describe("Chat workspace", () => {
  test.beforeEach(async ({ page }) => {
    mockAllAPIs(page);
    await enableAuthBypass(page);
  });

  test("new chat page loads with input box", async ({ page }) => {
    await page.goto(`/workspace/chats/${MOCK_THREAD_ID}`);

    const textarea = page.getByRole("textbox");
    await expect(textarea).toBeVisible({ timeout: 15_000 });
  });

  test("can type a message in the input box", async ({ page }) => {
    await page.goto(`/workspace/chats/${MOCK_THREAD_ID}`);

    const textarea = page.getByRole("textbox");
    await expect(textarea).toBeVisible({ timeout: 15_000 });

    await textarea.fill("分析茅台股票");
    await expect(textarea).toHaveValue("分析茅台股票");
  });

  test("sending a message triggers SSE stream and shows AI response", async ({
    page,
  }) => {
    let streamCalled = false;
    await page.route("**/api/threads/*/runs/stream", (route) => {
      streamCalled = true;
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [
          `event: metadata\ndata: ${JSON.stringify({ run_id: "run-1", thread_id: MOCK_THREAD_ID })}\n\n`,
          `event: values\ndata: ${JSON.stringify({
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
          })}\n\n`,
          `event: end\ndata: {}\n\n`,
        ].join(""),
      });
    });

    await page.goto(`/workspace/chats/${MOCK_THREAD_ID}`);

    const textarea = page.getByRole("textbox");
    await expect(textarea).toBeVisible({ timeout: 15_000 });

    await textarea.fill("分析茅台");
    await textarea.press("Enter");

    await expect.poll(() => streamCalled, { timeout: 10_000 }).toBeTruthy();

    await expect(page.getByText("Quant Agent 分析完成！")).toBeVisible({
      timeout: 10_000,
    });
  });

  test("tool call messages are rendered", async ({ page }) => {
    await page.route("**/api/threads/*/runs/stream", handleRunStreamWithTools);

    await page.goto(`/workspace/chats/${MOCK_THREAD_ID}`);

    const textarea = page.getByRole("textbox");
    await expect(textarea).toBeVisible({ timeout: 15_000 });

    await textarea.fill("分析茅台股票");
    await textarea.press("Enter");

    // AI final response should appear
    await expect(
      page.getByText("茅台当前价格 1800 元，成交量 12345 手。"),
    ).toBeVisible({ timeout: 10_000 });
  });

  test("Shift+Enter creates newline without sending", async ({ page }) => {
    await page.goto(`/workspace/chats/${MOCK_THREAD_ID}`);

    const textarea = page.getByRole("textbox");
    await expect(textarea).toBeVisible({ timeout: 15_000 });

    await textarea.fill("第一行");
    await textarea.press("Shift+Enter");
    await textarea.type("第二行");

    const value = await textarea.inputValue();
    expect(value).toContain("第一行");
    expect(value).toContain("第二行");

    // Should not have triggered a stream call
    // (no AI response should appear)
    await expect(page.getByText("Quant Agent 分析完成！")).not.toBeVisible();
  });

  test("human message appears immediately as optimistic update", async ({
    page,
  }) => {
    // Delay the stream response to observe optimistic message
    let releaseStream!: () => void;
    const streamPromise = new Promise<void>((resolve) => {
      releaseStream = resolve;
    });

    await page.route("**/api/threads/*/runs/stream", async (route) => {
      await streamPromise;
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [
          `event: metadata\ndata: ${JSON.stringify({ run_id: "run-1", thread_id: MOCK_THREAD_ID })}\n\n`,
          `event: values\ndata: ${JSON.stringify({
            messages: [
              {
                type: "human",
                id: "msg-human-1",
                content: [{ type: "text", text: "Hello" }],
              },
              {
                type: "ai",
                id: "msg-ai-1",
                content: "Response",
              },
            ],
          })}\n\n`,
          `event: end\ndata: {}\n\n`,
        ].join(""),
      });
    });

    await page.goto(`/workspace/chats/${MOCK_THREAD_ID}`);

    const textarea = page.getByRole("textbox");
    await expect(textarea).toBeVisible({ timeout: 15_000 });

    await textarea.fill("分析茅台");
    await textarea.press("Enter");

    // Human message should appear immediately (optimistic)
    await expect(page.getByText("分析茅台")).toBeVisible({ timeout: 5_000 });

    // Release the stream
    releaseStream();
  });
});
