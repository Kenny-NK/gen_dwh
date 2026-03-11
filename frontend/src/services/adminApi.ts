import api from "./api";

export type AdminTenant = {
  id: string;
  name: string;
  subdomain: string;
  schema_name: string;
  keycloak_realm: string | null;
  is_active: boolean;
  deleted_at: string | null;
};

export type AdminMembership = {
  id: string;
  tenant_id: string;
  tenant_name: string;
  tenant_subdomain: string;
  role: "owner" | "user" | "viewer";
  revoked_at: string | null;
  deleted_at: string | null;
};

export type AdminUser = {
  id: string;
  keycloak_id: string;
  email: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  memberships: AdminMembership[];
};

export type AdminUsersResponse = {
  items: AdminUser[];
  total: number;
  available_roles: Array<"owner" | "user" | "viewer">;
};

export async function getAdminTenants(): Promise<AdminTenant[]> {
  const response = await api.get("/admin/tenants");
  return response.data.items ?? [];
}

export async function createAdminTenant(payload: {
  name: string;
  subdomain: string;
  schema_name?: string;
  keycloak_realm?: string;
  is_active: boolean;
}): Promise<AdminTenant> {
  const response = await api.post("/admin/tenants", payload);
  return response.data;
}

export async function updateAdminTenant(
  tenantId: string,
  payload: Partial<{
    name: string;
    subdomain: string;
    keycloak_realm: string;
    is_active: boolean;
  }>
): Promise<AdminTenant> {
  const response = await api.patch(`/admin/tenants/${tenantId}`, payload);
  return response.data;
}

export async function deleteAdminTenant(tenantId: string): Promise<void> {
  await api.delete(`/admin/tenants/${tenantId}`);
}

export async function getAdminUsers(params: {
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<AdminUsersResponse> {
  const response = await api.get("/admin/users", { params });
  return response.data;
}

export async function createAdminUser(payload: {
  keycloak_id: string;
  email: string;
  is_active: boolean;
}): Promise<AdminUser> {
  const response = await api.post("/admin/users", payload);
  return response.data;
}

export async function updateAdminUser(
  userId: string,
  payload: Partial<{
    keycloak_id: string;
    email: string;
    is_active: boolean;
  }>
): Promise<AdminUser> {
  const response = await api.patch(`/admin/users/${userId}`, payload);
  return response.data;
}

export async function deleteAdminUser(userId: string): Promise<void> {
  await api.delete(`/admin/users/${userId}`);
}

export async function upsertAdminMembership(payload: {
  userId: string;
  tenantId: string;
  role: "owner" | "user" | "viewer";
}): Promise<AdminUser> {
  const response = await api.put(`/admin/users/${payload.userId}/memberships`, {
    tenant_id: payload.tenantId,
    role: payload.role,
  });
  return response.data;
}

export async function deleteAdminMembership(payload: {
  userId: string;
  membershipId: string;
}): Promise<void> {
  await api.delete(`/admin/users/${payload.userId}/memberships/${payload.membershipId}`);
}
