import { expect, test } from "@playwright/test";

import { enableAuthBypass, mockAuthAPI } from "./utils/mock-api";

test.describe("Setup flow", () => {
  test("setup page renders with system setup heading", async ({ page }) => {
    mockAuthAPI(page, { setupStatus: { needs_setup: true } });
    await page.goto("/setup");

    await expect(page.getByText("System Setup")).toBeVisible();
    await expect(
      page.getByText("Create the first admin account"),
    ).toBeVisible();
  });

  test("setup page has all required input fields", async ({ page }) => {
    mockAuthAPI(page, { setupStatus: { needs_setup: true } });
    await page.goto("/setup");

    await expect(page.getByLabel("Full Name")).toBeVisible();
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Initialize System" }),
    ).toBeVisible();
  });

  test("successful initialization redirects to /workspace", async ({
    page,
  }) => {
    mockAuthAPI(page, { setupStatus: { needs_setup: true } });
    await page.goto("/setup");

    await page.getByLabel("Full Name").fill("Admin User");
    await page.getByLabel("Email").fill("admin@example.com");
    await page.getByLabel("Password").fill("adminpass123");
    await page.getByRole("button", { name: "Initialize System" }).click();

    // Set bypass cookie so workspace SSR auth guard passes
    await enableAuthBypass(page);

    await page.waitForURL("**/workspace", { timeout: 10_000 });
    expect(page.url()).toContain("/workspace");
  });

  test("initialization failure shows error message", async ({ page }) => {
    mockAuthAPI(page, { setupStatus: { needs_setup: true } });

    await page.route("**/api/v1/auth/initialize", (route) => {
      if (route.request().method() === "POST") {
        return route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({ detail: "System already initialized" }),
        });
      }
      return route.fallback();
    });

    await page.goto("/setup");

    await page.getByLabel("Full Name").fill("Admin");
    await page.getByLabel("Email").fill("admin@example.com");
    await page.getByLabel("Password").fill("adminpass123");
    await page.getByRole("button", { name: "Initialize System" }).click();

    await expect(page.getByText("System already initialized")).toBeVisible({
      timeout: 5_000,
    });
  });
});
