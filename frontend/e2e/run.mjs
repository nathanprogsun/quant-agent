import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ensureBackend, ensureFrontend, stopAll } from "./harness.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const testFiles = fs
  .readdirSync(__dirname)
  .filter((f) => f.endsWith(".test.mjs"))
  .map((f) => path.join(__dirname, f));

await ensureBackend();
await ensureFrontend();

console.log(`[e2e] running ${testFiles.length} test file(s) serially...`);

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

await stopAll();
process.exit(code);
