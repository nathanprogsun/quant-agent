import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = path.resolve(__dirname, "..", "..");
export const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
export const FRONTEND_URL = process.env.FRONTEND_URL ?? "http://127.0.0.1:3000";

// Services spawned by this harness. We kill them (and their whole process
// group) on cleanup so children like `uv run uvicorn` -> python don't survive.
const children = [];

function waitForUp(url, timeout = 180000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const tick = async () => {
      try {
        await fetch(url, { redirect: "manual" });
        return resolve();
      } catch {
        if (Date.now() - start > timeout) {
          return reject(new Error(`timeout waiting for ${url}`));
        }
        setTimeout(tick, 500);
      }
    };
    tick();
  });
}

async function portInUse(url) {
  try {
    await fetch(url, { redirect: "manual" });
    return true;
  } catch {
    return false;
  }
}

/**
 * Start backend on an isolated sqlite test DB. Refuses to reuse a foreign
 * backend already listening on :8000 (we can't know which DB it uses, and a
 * stale/orphan backend on :8000 is exactly the bug we're avoiding). Set
 * E2E_REUSE_BACKEND=1 to force reuse (e.g. you've started your own backend and
 * want E2E to hit it directly).
 */
export async function ensureBackend() {
  if (process.env.E2E_REUSE_BACKEND === "1") {
    if (await portInUse(`${BACKEND_URL}/health`)) {
      console.log(`[e2e] reuse backend (E2E_REUSE_BACKEND=1) ${BACKEND_URL}`);
      return;
    }
    throw new Error(
      "E2E_REUSE_BACKEND=1 but nothing healthy at " +
        BACKEND_URL +
        "/health — start your backend first, or unset E2E_REUSE_BACKEND.",
    );
  }
  if (await portInUse(`${BACKEND_URL}/health`)) {
    throw new Error(
      `Port-in-use guard: something is already serving ${BACKEND_URL}. ` +
        "This harness refuses to reuse a foreign backend (its database is " +
        "unknown and E2E must use an isolated test DB). Either:\n" +
        "  - stop the existing backend on :8000, or\n" +
        "  - set E2E_REUSE_BACKEND=1 if you genuinely want to reuse it.",
    );
  }
  console.log("[e2e] starting backend (uvicorn :8000, isolated sqlite test db)...");
  const dbPath = path.join(os.tmpdir(), `quant-agent-e2e-${process.pid}.sqlite`);
  const cpPath = path.join(os.tmpdir(), `quant-agent-e2e-${process.pid}-checkpoints.db`);
  // detached: true creates a new process group so we can kill the whole tree
  // (uv run -> python uvicorn) without leaving orphans.
  const child = spawn(
    "uv",
    ["run", "uvicorn", "app.web.application:app", "--port", "8000", "--host", "127.0.0.1"],
    {
      cwd: path.join(REPO_ROOT, "backend"),
      env: {
        ...process.env,
        DATABASE_URL: `sqlite+aiosqlite:///${dbPath}`,
        CHECKPOINTER_CONNECTION_STRING: cpPath,
      },
      stdio: ["ignore", "pipe", "pipe"],
      detached: true,
    },
  );
  child.stdout.on("data", (d) => process.stdout.write(`[backend] ${d}`));
  child.stderr.on("data", (d) => process.stderr.write(`[backend] ${d}`));
  children.push(child);
  await waitForUp(`${BACKEND_URL}/health`);
  console.log(`[e2e] backend ready (test db: ${dbPath})`);
}

/**
 * Start frontend if nothing is on :3000. If something is already there, reuse
 * it (frontend dev server reuse is safe — it proxies /api to BACKEND_URL and
 * doesn't carry state we care about). Set E2E_REUSE_FRONTEND=0 to never reuse.
 */
export async function ensureFrontend() {
  const reuseOk = process.env.E2E_REUSE_FRONTEND !== "0";
  if (reuseOk && (await portInUse(FRONTEND_URL))) {
    console.log(`[e2e] reuse frontend ${FRONTEND_URL}`);
    return;
  }
  console.log("[e2e] starting frontend (pnpm dev :3000)...");
  const child = spawn("pnpm", ["dev"], {
    cwd: path.join(REPO_ROOT, "frontend"),
    env: process.env,
    stdio: ["ignore", "pipe", "pipe"],
    detached: true,
  });
  child.stdout.on("data", (d) => process.stdout.write(`[frontend] ${d}`));
  child.stderr.on("data", (d) => process.stderr.write(`[frontend] ${d}`));
  children.push(child);
  await waitForUp(FRONTEND_URL);
  console.log(`[e2e] frontend ready ${FRONTEND_URL}`);
}

let stopped = false;
export async function stopAll() {
  if (stopped) return;
  stopped = true;
  // Kill the whole process group (negative pid) so `uv run` -> python
  // children die together and never become orphans.
  for (const c of children) {
    try {
      process.kill(-c.pid, "SIGTERM");
    } catch {
      try {
        c.kill("SIGTERM");
      } catch {
        // ignore
      }
    }
  }
  await new Promise((r) => setTimeout(r, 1500));
  for (const c of children) {
    try {
      process.kill(-c.pid, "SIGKILL");
    } catch {
      try {
        if (!c.killed) c.kill("SIGKILL");
      } catch {
        // ignore
      }
    }
  }
  children.length = 0;
}