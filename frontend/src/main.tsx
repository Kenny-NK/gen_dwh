/**
 * App entry point with React Router and protected routes (T031).
 */

import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "react-oidc-context";
import { WebStorageStateStore } from "oidc-client-ts";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { Layout } from "./components/Layout";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ToastProvider } from "./components/common/Toast";
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
  userStore: new WebStorageStateStore({ store: window.sessionStorage }),
  automaticSilentRenew: true,
  redirect_uri: window.location.origin,
  post_logout_redirect_uri: window.location.origin,
  scope: "openid profile email",
  onSigninCallback: () => {
    window.history.replaceState({}, document.title, window.location.pathname);
  },
};

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isLoading, isAuthenticated, signinRedirect, signinSilent } = useAuth();
  const redirectStarted = React.useRef(false);

  React.useEffect(() => {
    if (!isLoading && !isAuthenticated && !redirectStarted.current) {
      redirectStarted.current = true;
      signinRedirect();
    }
  }, [isLoading, isAuthenticated, signinRedirect]);

  React.useEffect(() => {
    if (!isAuthenticated) return;
    const timer = window.setInterval(() => {
      void signinSilent().catch(() => {
        // Silent refresh failure is handled by normal auth guard redirect.
      });
    }, 5 * 60 * 1000);
    return () => window.clearInterval(timer);
  }, [isAuthenticated, signinSilent]);

  if (isLoading) {
    return <div className="flex h-screen items-center justify-center">Загрузка...</div>;
  }

  if (!isAuthenticated) {
    return <div className="flex h-screen items-center justify-center">Переход к авторизации...</div>;
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
