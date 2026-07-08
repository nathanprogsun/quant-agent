import puppeteer from "puppeteer-core";

const CHROME_PATH =
  process.env.PUPPETEER_EXECUTABLE_PATH ??
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const HEADLESS = process.env.PUPPETEER_HEADLESS !== "false";
const FRONTEND_URL = process.env.FRONTEND_URL ?? "http://127.0.0.1:3000";

export async function launchBrowser() {
  return puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: HEADLESS,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });
}

/**
 * Create an isolated browser context (incognito) + page so cookies from one
 * test (e.g. an authenticated access_token) do not leak into another test.
 * Caller must close the returned context when done.
 */
export async function isolatedPage(browser) {
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  return { context, page };
}

/**
 * Switch the LoginForm to register mode. Clicks the mode toggle only while the
 * form is still in login mode (so it never oscillates back), polling until the
 * register field (#fullName) appears. Robust against click-before-hydration.
 */
export async function switchToRegister(page, timeout = 30000) {
  await waitForReactReady(page);
  await page.waitForFunction(
    () => {
      if (document.querySelector("#fullName")) return true;
      const toggle = document.querySelector('button[type="button"]');
      const submit = document.querySelector('button[type="submit"]');
      if (toggle && submit && (submit.textContent || "").trim() === "登录") {
        toggle.click();
      }
      return !!document.querySelector("#fullName");
    },
    { timeout, polling: 200 },
  );
}

/**
 * Wait until React has attached a fiber to <html> (i.e. hydration has begun /
 * the client tree is mounted). Interactions (clicks) before this are no-ops.
 * Without allowedDevOrigins the dev build never hydrates, so this also
 * doubles as a guard against the hydration regression.
 */
export async function waitForReactReady(page, timeout = 30000) {
  await page.waitForFunction(
    () =>
      Object.keys(document.documentElement).some((k) => k.startsWith("__react")),
    { timeout, polling: 100 },
  );
}

/**
 * Create a real authenticated session by hitting the real backend register
 * endpoint through the frontend proxy, then inject the resulting access_token
 * cookie into the browser. This exercises the real backend auth + SSR auth +
 * workspace rendering end-to-end, sidestepping the (currently broken) login
 * form UI hydration — see auth.test.mjs for the LoginForm hydration bug.
 */
export async function createSession(page, password = "TestPassword123!") {
  const email = `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
  const r = await fetch(`${FRONTEND_URL}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: "E2E User" }),
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
  return email;
}
