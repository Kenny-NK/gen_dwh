import api from "./api";

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
};

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
