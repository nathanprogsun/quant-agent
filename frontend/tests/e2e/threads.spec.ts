import { expect, test } from "@playwright/test";

import {
  enableAuthBypass,
  mockAllAPIs,
  MOCK_THREAD_ID,
  MOCK_THREAD_ID_2,
} from "./utils/mock-api";

test.describe("Thread management", () => {
  test("sidebar shows thread list", async ({ page }) => {
    await enableAuthBypass(page);
    mockAllAPIs(page, {
      threads: [
        { thread_id: MOCK_THREAD_ID, title: "茅台分析" },
        { thread_id: MOCK_THREAD_ID_2, title: "A股行情" },
      ],
    });

    await page.goto(`/workspace/chats/${MOCK_THREAD_ID}`);

    // Use link selector to avoid matching the heading
    await expect(
      page.getByRole("link", { name: "茅台分析" }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByRole("link", { name: "A股行情" }),
    ).toBeVisible();
  });

  test("clicking a thread in sidebar navigates to it", async ({ page }) => {
    await enableAuthBypass(page);
    mockAllAPIs(page, {
      threads: [
        { thread_id: MOCK_THREAD_ID, title: "茅台分析" },
        { thread_id: MOCK_THREAD_ID_2, title: "A股行情" },
      ],
    });

    await page.goto(`/workspace/chats/${MOCK_THREAD_ID}`);
    await expect(
      page.getByRole("link", { name: "A股行情" }),
    ).toBeVisible({ timeout: 15_000 });

    await page.getByRole("link", { name: "A股行情" }).click();

    await page.waitForURL(`**/chats/${MOCK_THREAD_ID_2}`, { timeout: 10_000 });
    expect(page.url()).toContain(MOCK_THREAD_ID_2);
  });

  test("thread title is editable", async ({ page }) => {
    await enableAuthBypass(page);
    mockAllAPIs(page, {
      threads: [{ thread_id: MOCK_THREAD_ID, title: "原始标题" }],
    });

    await page.goto(`/workspace/chats/${MOCK_THREAD_ID}`);

    const title = page.getByRole("heading", { name: "原始标题" });
    await expect(title).toBeVisible({ timeout: 15_000 });

    // Click to edit
    await title.click();

    // The title input appears after clicking the heading
    const input = page.locator("input").first();
    await expect(input).toBeVisible({ timeout: 5_000 });

    // Clear and type new title
    await input.fill("新标题");
    await input.press("Enter");

    // Input should disappear (edit mode ends)
    await expect(input).toBeHidden({ timeout: 5_000 });
  });

  test("direct URL access loads thread", async ({ page }) => {
    await enableAuthBypass(page);
    mockAllAPIs(page, {
      threads: [
        {
          thread_id: MOCK_THREAD_ID,
          title: "直接访问测试",
          messages: [
            {
              type: "human",
              id: "msg-1",
              content: [{ type: "text", text: "历史消息" }],
            },
            {
              type: "ai",
              id: "msg-2",
              content: "历史回复",
            },
          ],
        },
      ],
    });

    await page.goto(`/workspace/chats/${MOCK_THREAD_ID}`);

    await expect(
      page.getByRole("heading", { name: "直接访问测试" }),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("workspace layout has sidebar with navigation", async ({ page }) => {
    await enableAuthBypass(page);
    mockAllAPIs(page, {
      threads: [{ thread_id: MOCK_THREAD_ID, title: "测试" }],
    });

    await page.goto(`/workspace/chats/${MOCK_THREAD_ID}`);

    await expect(page.getByText("Workspace")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("link", { name: "Chats" })).toBeVisible();
  });
});
