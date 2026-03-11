import { describe, expect, it } from "vitest";

import { getRunStatusUiConfig } from "./runStatus";

describe("getRunStatusUiConfig", () => {
  it("returns config for known statuses", () => {
    expect(getRunStatusUiConfig("running")).toMatchObject({
      label: "Выполняется",
      fallbackActivityLabel: "Идет обработка данных",
    });
  });

  it("falls back to pending config for unknown statuses", () => {
    expect(getRunStatusUiConfig("unknown")).toMatchObject({
      label: "Ожидание",
      fallbackActivityLabel: "Ожидание очереди",
    });
  });
});
