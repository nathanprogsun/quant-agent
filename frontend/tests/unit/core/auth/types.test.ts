import { describe, expect, test } from "vitest";

import { parseAuthError, userSchema } from "@/core/auth/types";

describe("userSchema", () => {
  test("validates a valid user", () => {
    const user = {
      id: "123e4567-e89b-12d3-a456-426614174000",
      email: "test@example.com",
      username: "testuser",
      full_name: "Test User",
      is_active: true,
      is_superuser: false,
    };

    const result = userSchema.safeParse(user);
    expect(result.success).toBe(true);
  });

  test("rejects invalid email", () => {
    const user = {
      id: "123e4567-e89b-12d3-a456-426614174000",
      email: "not-an-email",
      username: "testuser",
      full_name: "Test User",
      is_active: true,
      is_superuser: false,
    };

    const result = userSchema.safeParse(user);
    expect(result.success).toBe(false);
  });

  test("rejects invalid uuid", () => {
    const user = {
      id: "not-a-uuid",
      email: "test@example.com",
      username: "testuser",
      full_name: "Test User",
      is_active: true,
      is_superuser: false,
    };

    const result = userSchema.safeParse(user);
    expect(result.success).toBe(false);
  });

  test("accepts null for nullable fields", () => {
    const user = {
      id: "123e4567-e89b-12d3-a456-426614174000",
      email: "test@example.com",
      username: null,
      full_name: null,
      is_active: true,
      is_superuser: false,
    };

    const result = userSchema.safeParse(user);
    expect(result.success).toBe(true);
  });

  test("rejects missing required fields", () => {
    const result = userSchema.safeParse({ email: "test@example.com" });
    expect(result.success).toBe(false);
  });
});

describe("parseAuthError", () => {
  test("extracts message from Error instance", () => {
    expect(parseAuthError(new Error("failed"))).toBe("failed");
  });

  test("returns string as-is", () => {
    expect(parseAuthError("failed")).toBe("failed");
  });

  test("returns fallback for unknown types", () => {
    expect(parseAuthError(42)).toBe("An unknown error occurred");
  });

  test("returns fallback for null", () => {
    expect(parseAuthError(null)).toBe("An unknown error occurred");
  });
});
