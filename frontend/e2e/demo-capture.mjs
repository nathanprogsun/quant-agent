// @ts-check
/**
 * demo-capture.mjs — drive the real QuantAgent stack with puppeteer (real
 * backend + real LLM + real jqcli, no mocks) and capture a sequence of page
 * screenshots that prove the documented features. Output PNGs land in
 * `frontend/public/screenshots/` for the README demo section.
 *
 * Why puppeteer (page.screenshot) instead of OS-level screencapture:
 *  `screencapture` captures the entire macOS desktop, leaking anything else
 *  on screen (chat apps, password managers, etc.). puppeteer is confined to
 *  the page it loaded — only the demo screenshots land on disk, nothing
 *  else.
 *
 * Flow captured (matches docs/spec.md F1–F3):
 *  01-home.png             — homepage with QuantAgent prompt input (F1 entry)
 *  02-prompt-typed.png     — same page with the strategy prompt filled in
 *  03-chat-with-code.png   — chat thread, LLM reply with strategy code card
 *  04-strategy-workspace.png— split-pane strategy editor opened (F1 result)
 *  05-backtest-submitted.png — "回测进行中" pill after real jqcli submit (F2)
 *
 * Both server processes use the e2e harness helpers (isolated sqlite DB,
 * refuses to reuse a foreign backend on :8000). Kill the harness on every
 * exit path.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

import {
  ensureBackend,
  ensureFrontend,
  stopAll,
  FRONTEND_URL,
  REPO_ROOT,
} from "./harness.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCREEN_DIR = path.resolve(__dirname, "..", "public", "screenshots");

const PROMPT =
  "写一个沪深300 ETF均线金叉死叉策略，回测最近1年，初始资金10万";

const CHROME_PATH =
  process.env.PUPPETEER_EXECUTABLE_PATH ??
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

let cleaned = false;
async function cleanup(code = 1) {
  if (cleaned) return;
  cleaned = true;
  await stopAll();
  process.exit(code);
}
process.on("SIGINT", () => cleanup(130));
process.on("SIGTERM", () => cleanup(143));
process.on("unhandledRejection", (e) => {
  console.error("[demo] unhandled:", e);
  cleanup(1);
});

const T0 = Date.now();
function log(stage, msg) {
  const dt = ((Date.now() - T0) / 1000).toFixed(1).padStart(5, " ");
  console.log(`[demo][${dt}s][${stage}] ${msg}`);
}

async function shoot(page, name) {
  fs.mkdirSync(SCREEN_DIR, { recursive: true });
  const out = path.join(SCREEN_DIR, name);
  await page.screenshot({ path: out, type: "png" });
  log("shot", `${name} (${(fs.statSync(out).size / 1024).toFixed(0)} KiB)`);
}

async function waitForHydrated(page) {
  await page.waitForFunction(
    () => Object.keys(document.documentElement).some((k) => k.startsWith("__react")),
    { timeout: 30_000, polling: 100 },
  );
}

async function waitForTextarea(page) {
  await page.waitForSelector("textarea", { timeout: 30_000 });
}

async function waitForChatUrl(page, timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (/\/workspace\/chats\/.+/.test(page.url())) return page.url();
    await new Promise((r) => setTimeout(r, 200));
  }
  return null;
}

async function run() {
  log("boot", "ensureBackend()");
  await ensureBackend();
  log("boot", "ensureFrontend()");
  await ensureFrontend();
  log("boot", "services ready");

  const email = `demo-${Date.now()}@quantagent.io`;
  const reg = await fetch(`${FRONTEND_URL}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      password: "DemoPassword123!",
      full_name: "Demo User",
    }),
  });
  if (!reg.ok) throw new Error(`register failed: ${reg.status} ${await reg.text()}`);
  log("auth", `registered ${email}`);
  const setCookie = reg.headers.get("set-cookie") ?? "";
  const m = setCookie.match(/access_token=([^;]+)/);
  if (!m) throw new Error("register response missing access_token cookie");
  const token = m[1];

  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
    defaultViewport: { width: 1280, height: 800, deviceScaleFactor: 1 },
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 800, deviceScaleFactor: 1 });
    await page.setCookie({
      name: "access_token",
      value: token,
      domain: "127.0.0.1",
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
    });

    // 01 — workspace home (authenticated user lands on /workspace prompt)
    log("ui", "goto /workspace");
    await page.goto(`${FRONTEND_URL}/workspace`, {
      waitUntil: "domcontentloaded",
      timeout: 30_000,
    });
    await waitForHydrated(page);
    await waitForTextarea(page);
    await new Promise((r) => setTimeout(r, 400));
    await shoot(page, "01-home.png");

    // 02 — prompt filled into textarea
    log("ui", "typing prompt");
    await page.click("textarea");
    await page.type("textarea", PROMPT, { delay: 10 });
    await new Promise((r) => setTimeout(r, 300));
    await shoot(page, "02-prompt-typed.png");

    // 03 — submit and let LLM stream. After the click the SPA routes to a
    // chat thread; SSE delivers tokens for ~10–60s. Snap mid-stream.
    log("ui", "clicking send");
    await page.click('button[aria-label="发送"]');
    const url = await waitForChatUrl(page);
    if (!url) throw new Error(`did not navigate to chat: ${page.url()}`);
    log("ui", `navigated to ${new URL(url).pathname}`);

    // Diagnostic dump so we know what the chat page actually looks like
    // before we start polling / snapping.
    await new Promise((r) => setTimeout(r, 800));
    try {
      const debug = await page.evaluate(() => ({
        url: location.href,
        title: document.title,
        bodyLen: (document.body.innerText || "").length,
        bodyHead: (document.body.innerText || "").slice(0, 200),
        preCount: document.querySelectorAll("pre").length,
        preLen: document.querySelector("pre")?.textContent?.trim().length ?? 0,
        textareaCount: document.querySelectorAll("textarea").length,
        strategyBtn: Array.from(document.querySelectorAll("button"))
          .filter((b) => /运行策略/.test(b.textContent || ""))
          .map((b) => ({ text: b.textContent, disabled: b.disabled })),
      }));
      log("dbg", JSON.stringify(debug));
      // save the initial HTML so we can debug offline if needed
      const html = await page.content();
      const dbgPath = path.join(SCREEN_DIR, "_debug-chat-page.html");
      fs.writeFileSync(dbgPath, html);
      log("dbg", `wrote ${dbgPath} (${(html.length / 1024).toFixed(0)} KiB)`);
    } catch (e) {
      log("dbg", `eval failed: ${e?.message?.slice(0, 80)}`);
    }

    // Wait for the chat layout to mount and the assistant reply to finish
    // streaming. StrategyCodeCard (the inline "打开策略代码" button) is the
    // canonical signal that the LLM emitted the strategy code — once it
    // exists in the chat, the assistant turn is effectively complete.
    // OpenAI keeps the SSE connection alive for ~90s between tool rounds, so
    // give the LLM up to 150s before declaring timeout (a single tool round
    // of jq_kb retrievals + RAG already eats ~30s in the logs).
    const cardDeadline = Date.now() + 150_000;
    let codeCard = false;
    while (Date.now() < cardDeadline) {
      try {
        codeCard = await page.evaluate(
          () =>
            !!document.querySelector(
              'button[aria-label="打开策略代码"]',
            ),
        );
        if (codeCard) break;
      } catch {
        /* route rewrite */
      }
      await new Promise((r) => setTimeout(r, 1_000));
    }
    log("ui", `strategy code card visible: ${codeCard}`);
    if (codeCard) await new Promise((r) => setTimeout(r, 2_500));
    await shoot(page, "03-chat-with-code.png");

    // 04 — open the strategy code card so the split-pane strategy workspace
    // renders, then snap. This is the user's first interaction after the
    // code arrives; the same flow powers the strategy editor + the
    // "运行策略" submit button later in the demo.
    let opened = false;
    for (let i = 0; i < 10; i += 1) {
      try {
        opened = await page.evaluate(() => {
          const btn = document.querySelector(
            'button[aria-label="打开策略代码"]',
          );
          if (!btn) return false;
          btn.click();
          return true;
        });
        if (opened) break;
      } catch {
        /* route rewrite */
      }
      await new Promise((r) => setTimeout(r, 250));
    }
    log("ui", `opened strategy card: ${opened}`);
    if (opened) await new Promise((r) => setTimeout(r, 1_500));
    await shoot(page, "04-strategy-workspace.png");

    // 05 — click "运行策略" and snap the running-pill state. The right pane
    // header shows "回测进行中" once submission has registered.
    let clicked = false;
    for (let i = 0; i < 20; i += 1) {
      try {
        clicked = await page.evaluate(() => {
          const btns = Array.from(document.querySelectorAll("button"));
          const btn = btns.find(
            (b) => /运行策略/.test(b.textContent || "") && !b.disabled,
          );
          if (!btn) return false;
          btn.click();
          return true;
        });
        if (clicked) break;
      } catch {
        /* retry */
      }
      await new Promise((r) => setTimeout(r, 250));
    }
    log("ui", `clicked '运行策略': ${clicked}`);

    // Give the SSE → status pill pipeline a few seconds to update, then snap
    // regardless (a real jqcli backtest can run for minutes — we capture the
    // submission state, not the completion).
    await new Promise((r) => setTimeout(r, 6_000));
    await shoot(page, "05-backtest-submitted.png");

    await browser.close();
    log("done", `screenshots in ${path.relative(REPO_ROOT, SCREEN_DIR)}`);
    await cleanup(0);
  } catch (e) {
    try {
      await browser.close();
    } catch {}
    console.error("[demo] failed:", e);
    await cleanup(1);
  }
}

await run();
