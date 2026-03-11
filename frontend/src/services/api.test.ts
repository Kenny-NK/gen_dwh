import { describe, expect, it } from "vitest";

import { extractListResponse } from "./api";

describe("extractListResponse", () => {
  it("returns items and total from paginated payload", () => {
    expect(
      extractListResponse<{ id: string }>({
        items: [{ id: "1" }, { id: "2" }],
        total: 12,
      })
    ).toEqual({
      items: [{ id: "1" }, { id: "2" }],
      total: 12,
    });
  });

  it("falls back to array length for plain arrays", () => {
    expect(extractListResponse<number>([1, 2, 3])).toEqual({
      items: [1, 2, 3],
      total: 3,
    });
  });

  it("returns empty result for invalid payload", () => {
    expect(extractListResponse<string>(null)).toEqual({
      items: [],
      total: null,
    });
  });
});
