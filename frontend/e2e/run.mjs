import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ensureBackend, ensureFrontend, stopAll } from "./harness.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const isSmoke = process.env.E2E_SMOKE === "1";
const testFiles = fs
  .readdirSync(__dirname)
  .filter((f) => f.endsWith(".test.mjs"))
  .filter((f) => (isSmoke ? f === "auth.test.mjs" : true))
  .map((f) => path.join(__dirname, f));

// GUARANTEE cleanup on every exit path: normal exit, Ctrl-C (SIGINT), kill
// (SIGTERM), or uncaught error. NEVER leave a spawned backend orphaned on the
// user's machine stealing their :8000 again.
let cleaned = false;
async function cleanup(code) {
  if (cleaned) return;
  cleaned = true;
  await stopAll();
  process.exit(code ?? 1);
}
process.on("SIGINT", () => cleanup(130));
process.on("SIGTERM", () => cleanup(143));
process.on("exit", () => {
  if (!cleaned) stopAll();
});

try {
  await ensureBackend();
  await ensureFrontend();
} catch (e) {
  console.error(`[e2e] ${e.message}`);
  await cleanup(1);
}

console.log(
  `[e2e] running ${testFiles.length} test file(s)${isSmoke ? " (smoke)" : ""} serially...`,
);

let code = 0;
for (const file of testFiles) {
  await new Promise((resolve) => {
    const child = spawn(process.execPath, ["--test", file], {
      stdio: "inherit",
      env: {
        ...process.env,
        BACKEND_URL: process.env.BACKEND_URL ?? "http://127.0.0.1:8000",
        FRONTEND_URL: process.env.FRONTEND_URL ?? "http://127.0.0.1:3000",
      },
    });
    child.on("exit", (c) => {
      if (c) code = c;
      resolve();
    });
  });
}

await cleanup(code);