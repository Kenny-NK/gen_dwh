/**
 * Authentication hooks (T028).
 */

import { useAuth as useOidcAuth } from "react-oidc-context";
import { useCallback, useEffect, useMemo, useState } from "react";

import api from "../services/api";

type BackendMe = {
  id: string;
  email: string;
  role: string;
  roles: string[];
  workspace_id: string | null;
  permissions: string[];
  is_system_admin: boolean;
};

export function useAuth() {
  const auth = useOidcAuth();
  const [backendMe, setBackendMe] = useState<BackendMe | null>(null);

  const isAuthenticated = auth.isAuthenticated;
  const isLoading = auth.isLoading;
  const user = auth.user;

  const login = useCallback(() => {
    auth.signinRedirect();
  }, [auth]);

  const logout = useCallback(async () => {
    try {
      await api.delete("/auth/session");
      setBackendMe(null);
    } finally {
      await auth.signoutRedirect().catch(() => {
        auth.removeUser();
      });
    }
  }, [auth]);

  useEffect(() => {
    if (!isAuthenticated) {
      setBackendMe(null);
      return;
    }

    let cancelled = false;

    void api
      .get<BackendMe>("/auth/me")
      .then((response) => response.data)
      .then((payload) => {
        if (!cancelled) {
          setBackendMe(payload);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBackendMe(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  const userInfo = useMemo(() => {
    if (!user?.profile) return null;
    const profile = user.profile as Record<string, unknown>;
    const realmRoles = (
      profile.realm_access as { roles?: string[] } | undefined
    )?.roles || [];
    const roles = realmRoles.map((role) => String(role));
    const isSystemAdmin = roles.includes("system:admin") || roles.includes("admin");
    return {
      id: backendMe?.id ?? String(user.profile.sub),
      email: backendMe?.email ?? String(user.profile.email ?? ""),
      role: backendMe?.role ?? (isSystemAdmin ? "admin" : "user"),
      roles: backendMe?.roles ?? roles,
      isSystemAdmin: backendMe?.is_system_admin ?? isSystemAdmin,
      isAdmin: backendMe?.is_system_admin ?? isSystemAdmin,
      permissions: backendMe?.permissions ?? [],
      tenantId: backendMe?.workspace_id ?? ((profile.tenant_id as string) ?? ""),
    };
  }, [backendMe, user]);

  return { isAuthenticated, isLoading, user: userInfo, login, logout };
}
