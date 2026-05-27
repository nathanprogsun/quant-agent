import { expect, test } from "@playwright/test";

import { enableAuthBypass, mockAuthAPI } from "./utils/mock-api";

test.describe("Auth flow", () => {
  test("login page renders email/password inputs and sign-in button", async ({
    page,
  }) => {
    mockAuthAPI(page);
    await page.goto("/login");

    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign In" })).toBeVisible();
  });

  test("login page has register link", async ({ page }) => {
    mockAuthAPI(page);
    await page.goto("/login");

    await expect(page.getByRole("button", { name: "Register" })).toBeVisible();
  });

  test("clicking register shows full name field and create account button", async ({
    page,
  }) => {
    mockAuthAPI(page);
    await page.goto("/login");

    await page.getByRole("button", { name: "Register" }).click();

    await expect(page.getByLabel("Full Name")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Create Account" }),
    ).toBeVisible();
  });

  test("successful login redirects to /workspace", async ({ page }) => {
    mockAuthAPI(page);
    await page.goto("/login");

    await page.getByLabel("Email").fill("test@example.com");
    await page.getByLabel("Password").fill("password123");
    await page.getByRole("button", { name: "Sign In" }).click();

    // Set bypass cookie so workspace SSR auth guard passes
    await enableAuthBypass(page);

    await page.waitForURL("**/workspace", { timeout: 10_000 });
    expect(page.url()).toContain("/workspace");
  });

  test("login failure shows error message", async ({ page }) => {
    mockAuthAPI(page);

    // Override login to return 401
    await page.route("**/api/v1/auth/login", (route) => {
      if (route.request().method() === "POST") {
        return route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Invalid credentials" }),
        });
      }
      return route.fallback();
    });

    await page.goto("/login");

    await page.getByLabel("Email").fill("test@example.com");
    await page.getByLabel("Password").fill("wrongpassword");
    await page.getByRole("button", { name: "Sign In" }).click();

    await expect(page.getByText("Invalid credentials")).toBeVisible({
      timeout: 5_000,
    });
  });

  test("successful register redirects to /workspace", async ({ page }) => {
    mockAuthAPI(page);
    await page.goto("/login");

    await page.getByRole("button", { name: "Register" }).click();

    await page.getByLabel("Full Name").fill("Test User");
    await page.getByLabel("Email").fill("new@example.com");
    await page.getByLabel("Password").fill("password123");
    await page.getByRole("button", { name: "Create Account" }).click();

    // Set bypass cookie so workspace SSR auth guard passes
    await enableAuthBypass(page);

    await page.waitForURL("**/workspace", { timeout: 10_000 });
    expect(page.url()).toContain("/workspace");
  });
});
