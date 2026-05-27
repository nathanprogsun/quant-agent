import { expect, test } from "@playwright/test";

import { enableAuthBypass, mockAllAPIs, MOCK_THREAD_ID } from "./utils/mock-api";

test.describe("Reconnection", () => {
  test("page refresh restores messages from history", async ({ page }) => {
    await enableAuthBypass(page);
    mockAllAPIs(page, {
      threads: [
        {
          thread_id: MOCK_THREAD_ID,
          title: "重连测试",
          messages: [
            {
              type: "human",
              id: "msg-human-1",
              content: [{ type: "text", text: "茅台怎么样？" }],
            },
            {
              type: "ai",
              id: "msg-ai-1",
              content: "茅台当前表现良好。",
            },
          ],
        },
      ],
    });

    await page.goto(`/workspace/chats/${MOCK_THREAD_ID}`);

    // Verify messages load from history
    await expect(page.getByText("茅台怎么样？")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText("茅台当前表现良好。")).toBeVisible();

    // Refresh the page
    await page.reload();

    // Messages should still be visible after reconnection
    await expect(page.getByText("茅台怎么样？")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText("茅台当前表现良好。")).toBeVisible();
  });
});
