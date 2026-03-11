import { describe, expect, it } from "vitest";

import { isMaskedPreviewValue, stringifyPreviewValue } from "./previewValue";

describe("previewValue", () => {
  it("stringifies scalar values", () => {
    expect(stringifyPreviewValue("plain text")).toBe("plain text");
    expect(stringifyPreviewValue(42)).toBe("42");
    expect(stringifyPreviewValue(null)).toBe("");
  });

  it("stringifies objects as json", () => {
    expect(stringifyPreviewValue({ key: "value" })).toBe('{"key":"value"}');
    expect(stringifyPreviewValue(["a", "b"])).toBe('["a","b"]');
  });

  it("detects masked preview values", () => {
    expect(isMaskedPreviewValue("abc***def")).toBe(true);
    expect(isMaskedPreviewValue("plain text")).toBe(false);
    expect(isMaskedPreviewValue({})).toBe(false);
  });
});
