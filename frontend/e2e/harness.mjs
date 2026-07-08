import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = path.resolve(__dirname, "..", "..");
export const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
export const FRONTEND_URL = process.env.FRONTEND_URL ?? "http://127.0.0.1:3000";

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

export async function ensureBackend() {
  try {
    await fetch(`${BACKEND_URL}/health`);
    console.log(`[e2e] reuse backend ${BACKEND_URL}`);
    return;
  } catch {
    // not running, start it
  }
  console.log("[e2e] starting backend (uvicorn :8000, isolated sqlite test db)...");
  const dbPath = path.join(os.tmpdir(), `quant-agent-e2e-${process.pid}.sqlite`);
  const cpPath = path.join(os.tmpdir(), `quant-agent-e2e-${process.pid}-checkpoints.db`);
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
    },
  );
  child.stdout.on("data", (d) => process.stdout.write(`[backend] ${d}`));
  child.stderr.on("data", (d) => process.stderr.write(`[backend] ${d}`));
  children.push(child);
  await waitForUp(`${BACKEND_URL}/health`);
}

export async function ensureFrontend() {
  try {
    await fetch(FRONTEND_URL, { redirect: "manual" });
    console.log(`[e2e] reuse frontend ${FRONTEND_URL}`);
    return;
  } catch {
    // not running, start it
  }
  console.log("[e2e] starting frontend (pnpm dev :3000)...");
  const child = spawn("pnpm", ["dev"], {
    cwd: path.join(REPO_ROOT, "frontend"),
    env: process.env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  child.stdout.on("data", (d) => process.stdout.write(`[frontend] ${d}`));
  child.stderr.on("data", (d) => process.stderr.write(`[frontend] ${d}`));
  children.push(child);
  await waitForUp(FRONTEND_URL);
}

export async function stopAll() {
  for (const c of children) {
    try {
      c.kill("SIGTERM");
    } catch {
      // ignore
    }
  }
  await new Promise((r) => setTimeout(r, 1500));
  for (const c of children) {
    try {
      if (!c.killed) c.kill("SIGKILL");
    } catch {
      // ignore
    }
  }
  children.length = 0;
}
