import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { launchBrowser, createSession, waitForReactReady, isolatedPage } from "./helpers.mjs";

const FRONTEND_URL = process.env.FRONTEND_URL ?? "http://127.0.0.1:3000";

let browser;

before(async () => {
  browser = await launchBrowser();
});

after(async () => {
  await browser?.close();
});

test("send message creates a real thread and streams an assistant reply", async () => {
  const { context, page } = await isolatedPage(browser);
  try {
    await createSession(page);
    await page.goto(`${FRONTEND_URL}/workspace`, {
      waitUntil: "networkidle0",
      timeout: 30000,
    });
    await waitForReactReady(page);
    await page.waitForSelector("textarea");

    const text = `E2E hello ${Date.now()}`;
    await page.type("textarea", text);
    await page.click('button[aria-label="发送"]');

    // Real backend creates the thread and the app navigates to it. Poll
    // page.url() from Node (robust across client-side navigations, unlike
    // waitForFunction which can bind to a stale frame context).
    const navDeadline = Date.now() + 30000;
    while (Date.now() < navDeadline) {
      if (/\/workspace\/chats\/.+/.test(page.url())) break;
      await new Promise((r) => setTimeout(r, 200));
    }
    assert.match(page.url(), /\/workspace\/chats\/.+/, "did not navigate to a chat thread");

    // User message rendered into the page body (real, no mock).
    const userDeadline = Date.now() + 60000;
    while (Date.now() < userDeadline) {
      const body = await page.evaluate(() => document.body.innerText);
      if (body.includes(text)) break;
      await new Promise((r) => setTimeout(r, 300));
    }

    // Assistant reply streamed from the real backend LLM (body grows beyond
    // the user's message + page chrome).
    const asstDeadline = Date.now() + 120000;
    while (Date.now() < asstDeadline) {
      const len = await page.evaluate(() => document.body.innerText.trim().length);
      if (len > 200) break;
      await new Promise((r) => setTimeout(r, 500));
    }
    const finalBody = await page.evaluate(() => document.body.innerText);
    assert.ok(finalBody.includes(text), "user message not rendered");
    assert.ok(finalBody.trim().length > 200, "assistant reply not streamed");
  } finally {
    await context.close();
  }
});
