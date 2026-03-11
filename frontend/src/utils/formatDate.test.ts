import { describe, expect, it } from "vitest";

import { formatDateTime } from "./formatDate";

describe("formatDateTime", () => {
  it("returns fallback for empty values", () => {
    expect(formatDateTime(null)).toBe("—");
    expect(formatDateTime(undefined, "n/a")).toBe("n/a");
  });

  it("returns fallback for invalid dates", () => {
    expect(formatDateTime("not-a-date")).toBe("—");
  });

  it("formats valid ISO datetime", () => {
    expect(formatDateTime("2026-03-11T10:20:30Z")).toContain("11.03.2026");
  });
});
