import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { launchBrowser, createSession, switchToRegister, isolatedPage } from "./helpers.mjs";

const FRONTEND_URL = process.env.FRONTEND_URL ?? "http://127.0.0.1:3000";

let browser;

before(async () => {
  browser = await launchBrowser();
});

after(async () => {
  await browser?.close();
});

test("unauthenticated user is redirected from /workspace to /login", async () => {
  const { context, page } = await isolatedPage(browser);
  try {
    await page.goto(`${FRONTEND_URL}/workspace`, {
      waitUntil: "networkidle0",
      timeout: 20000,
    });
    assert.ok(
      page.url().includes("/login"),
      `expected redirect to /login, got ${page.url()}`,
    );
    const hasSubmit = await page.evaluate(
      () => !!document.querySelector('button[type="submit"]'),
    );
    assert.ok(hasSubmit, "login form submit button not found");
  } finally {
    await context.close();
  }
});

test("real backend session lands the user on the workspace", async () => {
  const { context, page } = await isolatedPage(browser);
  try {
    await createSession(page);
    await page.goto(`${FRONTEND_URL}/workspace`, {
      waitUntil: "networkidle0",
      timeout: 30000,
    });
    assert.ok(
      page.url().includes("/workspace") && !page.url().includes("/login"),
      `expected /workspace, got ${page.url()}`,
    );
    const body = await page.evaluate(() => document.body.innerText);
    assert.match(body, /JoinQuant|人工智能投研平台|量化/);
    const hasPrompt = await page.evaluate(() => !!document.querySelector("textarea"));
    assert.ok(hasPrompt, "workspace prompt input not found");
  } finally {
    await context.close();
  }
});

test("login form hydrates and the register toggle switches modes", async () => {
  const { context, page } = await isolatedPage(browser);
  try {
    await page.goto(`${FRONTEND_URL}/login`, { waitUntil: "networkidle0" });
    await switchToRegister(page);
    const switched = await page.evaluate(() => !!document.querySelector("#fullName"));
    assert.ok(switched, "register mode did not activate");
  } finally {
    await context.close();
  }
});
