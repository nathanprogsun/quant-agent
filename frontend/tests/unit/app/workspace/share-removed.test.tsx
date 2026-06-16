// @vitest-environment jsdom
import { describe, expect, test } from "vitest";

describe("share page removal", () => {
  test("share directory no longer exists on disk", async () => {
    const fs = await import("fs/promises");
    const path = await import("path");
    const sharePath = path.resolve(
      __dirname,
      "../../../../src/app/workspace/share",
    );
    await expect(fs.access(sharePath)).rejects.toThrow();
  });
});
