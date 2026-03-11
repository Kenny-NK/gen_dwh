import { describe, expect, it } from "vitest";

import {
  buildJiraPreviewPayload,
  defaultJiraExtractionConfig,
  getJiraPreviewStreamData,
  normalizeJiraExtractionConfig,
} from "./jiraApi";

describe("normalizeJiraExtractionConfig", () => {
  it("defaults to basic mode for empty configs", () => {
    expect(normalizeJiraExtractionConfig()).toEqual(defaultJiraExtractionConfig);
  });

  it("infers jql mode for legacy configs with jql", () => {
    expect(
      normalizeJiraExtractionConfig({
        streams: ["issues"],
        jql: 'project = DWHTOT ORDER BY created DESC',
      }).query_mode
    ).toBe("jql");
  });
});

describe("buildJiraPreviewPayload", () => {
  it("builds basic payload without jql", () => {
    expect(
      buildJiraPreviewPayload({
        query_mode: "basic",
        streams: ["issues"],
        project_keys: ["DWHTOT"],
        start_date: "2026-03-11T10:00:00.000Z",
        batch_size: 25,
      })
    ).toEqual({
      query_mode: "basic",
      streams: ["issues"],
      project_keys: ["DWHTOT"],
      start_date: "2026-03-11T10:00:00.000Z",
      batch_size: 25,
    });
  });

  it("builds jql payload without basic filters", () => {
    expect(
      buildJiraPreviewPayload({
        query_mode: "jql",
        streams: ["issues"],
        project_keys: ["DWHTOT"],
        start_date: "2026-03-11T10:00:00.000Z",
        jql: 'project = GEOPR ORDER BY created DESC',
        batch_size: 10,
      })
    ).toEqual({
      query_mode: "jql",
      streams: ["issues"],
      jql: 'project = GEOPR ORDER BY created DESC',
      batch_size: 10,
    });
  });
});

describe("getJiraPreviewStreamData", () => {
  it("prefers normalized preview fields when available", () => {
    expect(
      getJiraPreviewStreamData(
        {
          success: true,
          streams: ["issues"],
          records: { issues: [{ legacy: true }] },
          schema: { issues: { legacy: true } },
          record_count: 1,
          columns_by_stream: { issues: ["issue_id", "issue_key"] },
          rows_by_stream: { issues: [{ issue_id: "1", issue_key: "DWHTOT-1" }] },
          schema_by_stream: { issues: { schema: { type: "object" } } },
        },
        "issues"
      )
    ).toEqual({
      columns: ["issue_id", "issue_key"],
      rows: [{ issue_id: "1", issue_key: "DWHTOT-1" }],
      schema: { schema: { type: "object" } },
    });
  });
});
