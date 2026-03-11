/**
 * App entry point with React Router and protected routes (T031).
 */

import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "react-oidc-context";
import { WebStorageStateStore } from "oidc-client-ts";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { WorkspaceSelector } from "./components/auth/WorkspaceSelector";
import { Layout } from "./components/Layout";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ToastProvider } from "./components/common/Toast";
import "./i18n";
import api from "./services/api";
import { MemoryStateStore } from "./services/memoryStore";
import "./styles.css";

// Lazy-loaded pages
const Dashboard = React.lazy(() => import("./pages/Dashboard/Dashboard"));
const SourcesList = React.lazy(() => import("./pages/Sources/SourcesList"));
const SourceForm = React.lazy(() => import("./pages/Sources/SourceForm"));
const FlowsList = React.lazy(() => import("./pages/Flows/FlowsList"));
const FlowDetail = React.lazy(() => import("./pages/Flows/FlowDetail"));
const FlowCreate = React.lazy(() => import("./pages/Flows/FlowCreate"));
const RunsList = React.lazy(() => import("./pages/Runs/RunsList"));
const RunDetail = React.lazy(() => import("./pages/Runs/RunDetail"));
const AuditLog = React.lazy(() => import("./pages/Audit/AuditLog"));
const UsersRoles = React.lazy(() => import("./pages/Admin/UsersRoles"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        const status = (error as { response?: { status?: number } }).response?.status;
        if (status) {
          return false;
        }
        return failureCount < 1;
      },
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

const oidcConfig = {
  authority: import.meta.env.VITE_KEYCLOAK_URL
    ? `${import.meta.env.VITE_KEYCLOAK_URL}/realms/${import.meta.env.VITE_KEYCLOAK_REALM || "gendwh"}`
    : "http://localhost:8080/realms/gendwh",
  client_id: import.meta.env.VITE_KEYCLOAK_CLIENT_ID || "gendwh-app",
  userStore: new MemoryStateStore(),
  stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
  automaticSilentRenew: true,
  redirect_uri: window.location.origin,
  post_logout_redirect_uri: window.location.origin,
  scope: "openid profile email",
  onSigninCallback: () => {
    window.history.replaceState({}, document.title, window.location.pathname);
  },
};

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isLoading, isAuthenticated, signinRedirect, user, activeNavigator } = useAuth();
  const redirectStarted = React.useRef(false);
  const sessionInitialized = React.useRef(false);
  const [sessionReady, setSessionReady] = React.useState(false);
  const [sessionInitFailed, setSessionInitFailed] = React.useState(false);
  const [requiresWorkspaceSelection, setRequiresWorkspaceSelection] = React.useState(false);

  type SessionBootstrap = {
    status: string;
    active_workspace_id: string | null;
    workspace_count: number;
    requires_workspace_selection: boolean;
  };

  const initializeSession = React.useCallback(async (accessToken: string): Promise<SessionBootstrap> => {
    const retryableStatuses = new Set([502, 503, 504]);
    const maxAttempts = 12;

    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      try {
        const response = await api.post<SessionBootstrap>("/auth/session", undefined, {
          headers: {
            Authorization: `Bearer ${accessToken}`,
          },
        });
        return response.data;
      } catch (error) {
        const status = (error as { response?: { status?: number } }).response?.status;
        const shouldRetry = status === undefined || retryableStatuses.has(status);
        if (!shouldRetry || attempt === maxAttempts - 1) {
          throw new Error("Failed to initialize server session");
        }
      }

      await new Promise((resolve) => {
        const delayMs = Math.min(1000 * (attempt + 1), 5000);
        window.setTimeout(resolve, delayMs);
      });
    }

    throw new Error("Failed to initialize server session");
  }, []);

  React.useEffect(() => {
    if (isLoading || isAuthenticated) {
      return;
    }
    // During silent renew / callback transitions don't trigger an extra redirect.
    if (activeNavigator) {
      return;
    }
    // Avoid full-page redirect loops after the app has already established
    // the backend cookie session once.
    if (sessionInitialized.current) {
      return;
    }
    if (!redirectStarted.current) {
      redirectStarted.current = true;
      void signinRedirect();
    }
  }, [activeNavigator, isAuthenticated, isLoading, signinRedirect]);

  React.useEffect(() => {
    if (!isAuthenticated) {
      if (!sessionInitialized.current && !activeNavigator) {
        setSessionReady(false);
      }
      setSessionInitFailed(false);
      setRequiresWorkspaceSelection(false);
      return;
    }

    if (!user?.access_token) {
      if (!sessionInitialized.current) {
        setSessionReady(false);
      }
      return;
    }

    let cancelled = false;
    setSessionInitFailed(false);

    void initializeSession(user.access_token)
      .then((resp) => {
        if (!cancelled) {
          sessionInitialized.current = true;
          setRequiresWorkspaceSelection(Boolean(resp.requires_workspace_selection));
          setSessionReady(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          if (!sessionInitialized.current) {
            setSessionReady(false);
            setSessionInitFailed(true);
          }
        }
      })
      .finally(() => {
        // no-op: subsequent session sync should not unmount route content
      });

    return () => {
      cancelled = true;
    };
  }, [activeNavigator, initializeSession, isAuthenticated, user?.access_token]);

  if (isLoading) {
    return <div className="flex h-screen items-center justify-center">Загрузка...</div>;
  }

  if (!isAuthenticated) {
    return <div className="flex h-screen items-center justify-center">Переход к авторизации...</div>;
  }

  if (sessionInitFailed) {
    return (
      <div className="flex h-screen items-center justify-center">
        Не удалось инициализировать сессию. Обновите страницу.
      </div>
    );
  }

  if (!sessionReady) {
    return <div className="flex h-screen items-center justify-center">Инициализация сессии...</div>;
  }

  if (requiresWorkspaceSelection) {
    return <WorkspaceSelector />;
  }

  return <>{children}</>;
}

function App() {
  return (
    <ErrorBoundary>
      <React.Suspense
        fallback={<div className="flex h-screen items-center justify-center">Загрузка...</div>}
      >
        <Routes>
          <Route
            element={
              <ProtectedRoute>
                <Layout />
              </ProtectedRoute>
            }
          >
            <Route path="/" element={<Dashboard />} />
            <Route path="/sources" element={<SourcesList />} />
            <Route path="/sources/new" element={<SourceForm />} />
            <Route path="/sources/:id/edit" element={<SourceForm />} />
            <Route path="/flows" element={<FlowsList />} />
            <Route path="/flows/new" element={<FlowCreate />} />
            <Route path="/flows/:id" element={<FlowDetail />} />
            <Route path="/flows/:id/runs" element={<RunsList />} />
            <Route path="/runs" element={<RunsList />} />
            <Route path="/runs/:id" element={<RunDetail />} />
            <Route path="/admin/users-roles" element={<UsersRoles />} />
            <Route path="/audit" element={<AuditLog />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </React.Suspense>
    </ErrorBoundary>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider {...oidcConfig}>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </ToastProvider>
      </QueryClientProvider>
    </AuthProvider>
  </React.StrictMode>
);
