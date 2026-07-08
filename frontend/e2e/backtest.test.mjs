import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { launchBrowser, createSession, isolatedPage } from "./helpers.mjs";

const FRONTEND_URL = process.env.FRONTEND_URL ?? "http://127.0.0.1:3000";

let browser;

before(async () => {
  browser = await launchBrowser();
});

after(async () => {
  await browser?.close();
});

/** Create a real authenticated session; returns { token, email }. */
async function createSessionToken(page) {
  const email = `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
  const r = await fetch(`${FRONTEND_URL}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password: "TestPassword123!", full_name: "E2E User" }),
  });
  if (!r.ok) throw new Error(`register failed: ${r.status}`);
  const cookie = r.headers.get("set-cookie");
  const m = cookie?.match(/access_token=([^;]+)/);
  if (!m) throw new Error("register response missing access_token cookie");
  const token = m[1];
  await page.setCookie({
    name: "access_token",
    value: token,
    domain: "127.0.0.1",
    path: "/",
    httpOnly: true,
    sameSite: "Lax",
  });
  return { token, email };
}
async function submitBacktest(cookie, threadId, code) {
  const r = await fetch(`${FRONTEND_URL}/api/v1/backtest`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Cookie: `access_token=${cookie}`,
    },
    body: JSON.stringify({
      code,
      thread_id: threadId,
      version: 1,
      params: {
        start_date: "2024-01-01",
        end_date: "2024-01-10",
        initial_capital: 100000,
        frequency: "day",
        benchmark: "000300.XSHG",
      },
    }),
  });
  return { status: r.status, data: await r.json().catch(() => ({})) };
}

/** Cancel the active backtest lock for a thread via the frontend proxy. */
async function cancelThreadBacktest(cookie, threadId) {
  const r = await fetch(
    `${FRONTEND_URL}/api/v1/backtest/threads/${threadId}/cancel`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Cookie: `access_token=${cookie}`,
      },
    },
  );
  return { status: r.status, data: await r.json().catch(() => ({})) };
}

/** Create a thread via the real backend API. */
async function createThread(cookie) {
  const r = await fetch(`${FRONTEND_URL}/api/v1/threads`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Cookie: `access_token=${cookie}`,
    },
    body: JSON.stringify({ model_name: "gpt-4o-mini" }),
  });
  const data = await r.json();
  return data.id ?? data.thread_id;
}

const SIMPLE_STRATEGY = [
  "# -*- coding: utf-8 -*-",
  "from jqdata import *",
  "def initialize(context):",
  "    set_benchmark('000300.XSHG')",
  "    set_option('use_real_price', True)",
  "    run_daily(rebalance, time='9:30')",
  "def rebalance(context):",
  "    pass",
].join("\n");

test("backtest submit → 409 on duplicate → cancel → re-submit succeeds", async () => {
  const { context, page } = await isolatedPage(browser);
  try {
    // 1. Create a real session + thread.
    const { token } = await createSessionToken(page);
    assert.ok(token, "access_token not obtained");
    const threadId = await createThread(token);
    assert.ok(threadId, "thread creation failed");

    // 2. Submit a backtest (real jqcli) — should succeed.
    const submit1 = await submitBacktest(token, threadId, SIMPLE_STRATEGY);
    assert.equal(submit1.status, 200, `first submit failed: ${JSON.stringify(submit1.data)}`);
    assert.ok(submit1.data.backtest_id, "first submit missing backtest_id");

    // 3. Immediately re-submit to the same thread — should get 409.
    const submit2 = await submitBacktest(token, threadId, SIMPLE_STRATEGY);
    assert.equal(submit2.status, 409, `expected 409, got ${submit2.status}`);
    assert.match(
      submit2.data.error?.message ?? "",
      /进行中的回测/,
      "409 error message mismatch",
    );

    // 4. Cancel the active backtest lock for this thread.
    const cancel = await cancelThreadBacktest(token, threadId);
    assert.equal(cancel.status, 200, `cancel failed: ${cancel.status}`);
    assert.ok(cancel.data.cancelled, "cancel response not confirmed");

    // 5. Re-submit after cancel — should succeed (lock released).
    const submit3 = await submitBacktest(token, threadId, SIMPLE_STRATEGY);
    assert.equal(
      submit3.status,
      200,
      `re-submit after cancel failed: ${JSON.stringify(submit3.data)}`,
    );
    assert.ok(submit3.data.backtest_id, "re-submit missing backtest_id");
  } finally {
    await context.close();
  }
});