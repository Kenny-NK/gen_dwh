/**
 * Authentication hooks (T028).
 */

import { useAuth as useOidcAuth } from "react-oidc-context";
import { useCallback, useMemo } from "react";

export function useAuth() {
  const auth = useOidcAuth();

  const isAuthenticated = auth.isAuthenticated;
  const isLoading = auth.isLoading;
  const user = auth.user;

  const login = useCallback(() => {
    auth.signinRedirect();
  }, [auth]);

  const logout = useCallback(async () => {
    try {
      await fetch("/api/v1/auth/session", {
        method: "DELETE",
        credentials: "include",
      });
    } finally {
      await auth.signoutRedirect().catch(() => {
        auth.removeUser();
      });
    }
  }, [auth]);

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
