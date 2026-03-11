import api from "./api";

export type JiraQueryMode = "basic" | "jql";

export type JiraProject = {
  id: string;
  key: string;
  name: string;
  lead_display_name?: string | null;
  lead_account_id?: string | null;
};

export type JiraStreamMetadata = {
  name: string;
  display_name: string;
  description: string;
  replication_method: "INCREMENTAL" | "FULL_TABLE";
  replication_keys: string[];
  primary_keys: string[];
  parent_stream?: string | null;
  field_count: number;
};

export type JiraExtractionConfig = {
  auth_type?: "basic_token" | "basic_password" | "pat_bearer";
  query_mode: JiraQueryMode;
  streams: string[];
  start_date?: string | null;
  batch_size: number;
  project_keys: string[];
  incremental_enabled: boolean;
  replication_key: string;
  jql?: string | null;
};

export type JiraFlowStreamConfig = {
  stream: string;
  replication_method: "FULL_TABLE" | "INCREMENTAL";
  replication_key: string;
};

export type JiraPreviewResponse = {
  success: boolean;
  streams: string[];
  records: Record<string, Array<Record<string, unknown>>>;
  schema: Record<string, unknown>;
  record_count: number;
  effective_query_mode?: JiraQueryMode;
  effective_jql?: string | null;
  columns_by_stream?: Record<string, string[]>;
  rows_by_stream?: Record<string, Array<Record<string, unknown>>>;
  schema_by_stream?: Record<string, unknown>;
};

export const defaultJiraExtractionConfig: JiraExtractionConfig = {
  query_mode: "basic",
  streams: ["issues"],
  start_date: null,
  batch_size: 100,
  project_keys: [],
  incremental_enabled: false,
  replication_key: "updated",
  jql: "",
};

export function normalizeJiraExtractionConfig(
  config?: Partial<JiraExtractionConfig> | null
): JiraExtractionConfig {
  const normalizedQueryMode: JiraQueryMode =
    config?.query_mode === "jql" || (!config?.query_mode && (config?.jql ?? "").trim()) ? "jql" : "basic";

  return {
    ...defaultJiraExtractionConfig,
    ...config,
    query_mode: normalizedQueryMode,
    streams: config?.streams?.length ? config.streams : defaultJiraExtractionConfig.streams,
    project_keys: config?.project_keys ?? defaultJiraExtractionConfig.project_keys,
    batch_size: config?.batch_size ?? defaultJiraExtractionConfig.batch_size,
    incremental_enabled: config?.incremental_enabled ?? defaultJiraExtractionConfig.incremental_enabled,
    replication_key: config?.replication_key ?? defaultJiraExtractionConfig.replication_key,
    jql: config?.jql ?? defaultJiraExtractionConfig.jql,
    start_date: config?.start_date ?? defaultJiraExtractionConfig.start_date,
  };
}

export function buildJiraPreviewPayload(config?: Partial<JiraExtractionConfig>) {
  const normalized = normalizeJiraExtractionConfig(config);
  if (normalized.query_mode === "jql") {
    return {
      query_mode: "jql" as const,
      streams: normalized.streams,
      jql: normalized.jql ?? "",
      batch_size: normalized.batch_size,
    };
  }
  return {
    query_mode: "basic" as const,
    streams: normalized.streams,
    project_keys: normalized.project_keys,
    start_date: normalized.start_date ?? null,
    batch_size: normalized.batch_size,
  };
}

export function getJiraPreviewStreamData(
  preview: JiraPreviewResponse | undefined,
  streamName: string
): {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  schema: unknown;
} {
  if (!preview || !streamName) {
    return { columns: [], rows: [], schema: null };
  }
  return {
    columns: preview.columns_by_stream?.[streamName] ?? [],
    rows: preview.rows_by_stream?.[streamName] ?? preview.records?.[streamName] ?? [],
    schema: preview.schema_by_stream?.[streamName] ?? preview.schema?.[streamName] ?? null,
  };
}

export async function getJiraProjects(sourceId: string): Promise<JiraProject[]> {
  const response = await api.get(`/sources/${sourceId}/jira/projects`);
  return response.data.projects ?? [];
}

export async function getJiraStreams(sourceId: string): Promise<JiraStreamMetadata[]> {
  const response = await api.get(`/sources/${sourceId}/jira/streams`);
  return response.data.streams ?? [];
}

export async function getJiraStreamSchema(sourceId: string, streamName: string): Promise<unknown> {
  const response = await api.get(`/sources/${sourceId}/jira/streams/${streamName}/schema`);
  return response.data;
}

export async function updateJiraExtractionConfig(
  sourceId: string,
  payload: JiraExtractionConfig
): Promise<{ extraction_config: JiraExtractionConfig }> {
  const response = await api.patch(`/sources/${sourceId}/extraction-config`, payload);
  return response.data;
}

export async function runJiraPreview(
  sourceId: string,
  payload: Partial<JiraExtractionConfig>
): Promise<JiraPreviewResponse> {
  const response = await api.post(`/sources/${sourceId}/jira/preview`, payload);
  return response.data;
}
