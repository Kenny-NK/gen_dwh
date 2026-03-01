/**
 * Authentication hooks (T028).
 */

import { useAuth as useOidcAuth } from "react-oidc-context";
import { useCallback, useEffect, useMemo } from "react";

export function useAuth() {
  const auth = useOidcAuth();

  const isAuthenticated = auth.isAuthenticated;
  const isLoading = auth.isLoading;
  const user = auth.user;

  const login = useCallback(() => {
    auth.signinRedirect();
  }, [auth]);

  const logout = useCallback(() => {
    auth.removeUser();
    sessionStorage.removeItem("access_token");
  }, [auth]);

  useEffect(() => {
    if (user?.access_token) {
      sessionStorage.setItem("access_token", user.access_token);
    }
  }, [user?.access_token]);

  const userInfo = useMemo(() => {
    if (!user?.profile) return null;
    const profile = user.profile as Record<string, unknown>;
    const realmRoles = (
      profile.realm_access as { roles?: string[] } | undefined
    )?.roles || [];
    return {
      id: user.profile.sub,
      email: user.profile.email ?? "",
      role: realmRoles.includes("admin") ? "admin" : "user",
      tenantId: (profile.tenant_id as string) ?? "",
    };
  }, [user]);

  return { isAuthenticated, isLoading, user: userInfo, login, logout };
}
