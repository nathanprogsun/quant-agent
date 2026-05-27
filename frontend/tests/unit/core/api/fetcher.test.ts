// @vitest-environment jsdom
import { afterEach, describe, expect, test } from "vitest";

import { injectCsrfHeader, readCsrfCookie } from "@/core/api/fetcher";

describe("readCsrfCookie", () => {
  afterEach(() => {
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  test("returns token when csrf_token cookie exists", () => {
    document.cookie = "csrf_token=abc123; path=/";
    expect(readCsrfCookie()).toBe("abc123");
  });

  test("returns null when csrf_token cookie is missing", () => {
    document.cookie = "other=value; path=/";
    expect(readCsrfCookie()).toBeNull();
  });

  test("handles URL-encoded token", () => {
    document.cookie = "csrf_token=abc%20123; path=/";
    expect(readCsrfCookie()).toBe("abc 123");
  });
});

describe("injectCsrfHeader", () => {
  afterEach(() => {
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  test("adds X-CSRF-Token header for POST requests", () => {
    document.cookie = "csrf_token=test-token; path=/";
    const url = new URL("https://example.com/api");
    const init: RequestInit = { method: "POST" };

    const result = injectCsrfHeader(url, init);
    const headers = new Headers(result.headers);

    expect(headers.get("X-CSRF-Token")).toBe("test-token");
  });

  test("skips header for GET requests", () => {
    document.cookie = "csrf_token=test-token; path=/";
    const url = new URL("https://example.com/api");
    const init: RequestInit = { method: "GET" };

    const result = injectCsrfHeader(url, init);
    const headers = new Headers(result.headers);

    expect(headers.has("X-CSRF-Token")).toBe(false);
  });

  test("does not overwrite existing X-CSRF-Token header", () => {
    document.cookie = "csrf_token=from-cookie; path=/";
    const url = new URL("https://example.com/api");
    const init: RequestInit = {
      method: "POST",
      headers: { "X-CSRF-Token": "from-header" },
    };

    const result = injectCsrfHeader(url, init);
    const headers = new Headers(result.headers);

    expect(headers.get("X-CSRF-Token")).toBe("from-header");
  });

  test("returns init unchanged when no csrf cookie", () => {
    const url = new URL("https://example.com/api");
    const init: RequestInit = { method: "POST" };

    const result = injectCsrfHeader(url, init);
    const headers = new Headers(result.headers);

    expect(headers.has("X-CSRF-Token")).toBe(false);
  });
});
