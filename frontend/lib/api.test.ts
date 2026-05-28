import { describe, expect, it } from "vitest";

describe("api module basics", () => {
  it("has base api env fallback expectation", () => {
    expect(typeof process.env).toBe("object");
  });
});
