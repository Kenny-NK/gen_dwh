import api from "./api";

export type WorkspaceSummary = {
  id: string;
  slug: string;
  name: string;
  role: string;
};

export type WorkspacesResponse = {
  items: WorkspaceSummary[];
  active_workspace_id: string | null;
};

export type ActiveWorkspaceResponse = {
  id: string;
  slug: string;
  name: string;
  is_active: boolean;
};

export async function getAuthWorkspaces(): Promise<WorkspacesResponse> {
  const response = await api.get("/auth/workspaces");
  return response.data;
}

export async function getActiveWorkspace(): Promise<ActiveWorkspaceResponse> {
  const response = await api.get("/auth/workspace");
  return response.data;
}

export async function switchWorkspace(workspaceId: string): Promise<ActiveWorkspaceResponse> {
  const response = await api.post("/auth/switch-workspace", {
    workspace_id: workspaceId,
  });
  return response.data.active_workspace;
}
