import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? "github" : "html",
  timeout: 60_000,

  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  webServer: process.env.CI
    ? undefined
    : [
    {
      command:
        "cd ../backend && uv run alembic upgrade head && uv run uvicorn app.web.application:app --port 8000",
      url: "http://localhost:8000/health",
      reuseExistingServer: true,
      timeout: 120_000,
      env: {
        ...process.env,
        DATABASE_URL: "sqlite+aiosqlite:///./e2e-data.db",
        CHECKPOINTER_CONNECTION_STRING: "e2e-checkpoints.db",
      },
    },
    {
      command: "pnpm dev",
      url: "http://localhost:3000",
      reuseExistingServer: true,
      timeout: 120_000,
      env: {
        ...process.env,
        BACKEND_URL: "http://localhost:8000",
        SKIP_ENV_VALIDATION: "1",
      },
    },
  ],
});
