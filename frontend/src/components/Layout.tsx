import React from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../hooks/useAuth";
import { useTheme } from "../hooks/useTheme";
import { ApiErrorNotice } from "./common/ApiErrorNotice";
import { Modal } from "./common/Modal";
import { NotificationBell } from "./Notifications/NotificationBell";
import { getActiveWorkspace, getAuthWorkspaces, switchWorkspace } from "../services/authApi";

const primaryNavItems = [
  { path: "/", labelKey: "nav_dashboard" },
  { path: "/sources", labelKey: "nav_sources" },
  { path: "/flows", labelKey: "nav_flows" },
  { path: "/runs", labelKey: "nav_runs" },
];

const adminNavItems = [
  { path: "/admin/users-roles", labelKey: "nav_users_roles" },
  { path: "/audit", labelKey: "nav_audit" },
];

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v3M12 19v3M4.93 4.93l2.12 2.12M16.95 16.95l2.12 2.12M2 12h3M19 12h3M4.93 19.07l2.12-2.12M16.95 7.05l2.12-2.12" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
    </svg>
  );
}

function SidebarLink({
  to,
  label,
  isActive,
}: {
  to: string;
  label: string;
  isActive: boolean;
}) {
  return (
    <Link
      to={to}
      className={[
        "block rounded-xl px-3 py-2.5 text-sm font-medium tracking-[0.01em] transition",
        isActive
          ? "bg-cyan-400/15 text-cyan-200 shadow-[inset_0_0_0_1px_rgba(103,232,249,0.18)]"
          : "text-slate-200 hover:bg-slate-800/90 hover:text-white",
      ].join(" ")}
    >
      {label}
    </Link>
  );
}

export function Layout() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();
  const isAdmin = Boolean(user?.isAdmin || user?.isSystemAdmin || user?.role === "admin");
  const [workspaceModalOpen, setWorkspaceModalOpen] = React.useState(false);
  const { data: workspacesResponse } = useQuery({
    queryKey: ["auth-workspaces-layout"],
    queryFn: getAuthWorkspaces,
  });
  const { data: activeWorkspace } = useQuery({
    queryKey: ["auth-active-workspace"],
    queryFn: getActiveWorkspace,
    retry: false,
  });
  const switchMutation = useMutation({
    mutationFn: (workspaceId: string) => switchWorkspace(workspaceId),
    onSuccess: () => {
      window.location.assign("/");
    },
  });
  const workspaces = workspacesResponse?.items ?? [];
  const hasMultipleWorkspaces = workspaces.length > 1;

  return (
    <div className="flex min-h-screen bg-transparent">
      <aside className="flex w-72 shrink-0 flex-col border-r border-slate-800/60 bg-slate-950/95 text-white">
        <div className="border-b border-slate-800/80 px-6 py-5">
          <div className="text-xs font-semibold uppercase tracking-[0.34em] text-cyan-300/70">
            GenDWH
          </div>
          <h1 className="mt-3 text-xl font-semibold tracking-[0.02em] text-white">Control Center</h1>
          <p className="mt-2 max-w-[15rem] text-xs font-medium leading-5 text-slate-400">
            {t("nav_subtitle")}
          </p>
        </div>

        <nav className="flex-1 overflow-y-auto px-4 py-5">
          <div className="space-y-1.5">
            {primaryNavItems.map((item) => (
              <SidebarLink
                key={item.path}
                to={item.path}
                label={t(item.labelKey)}
                isActive={location.pathname === item.path || location.pathname.startsWith(`${item.path}/`)}
              />
            ))}
          </div>

          {isAdmin && (
            <div className="mt-8">
              <div className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">
                Admin
              </div>
              <div className="space-y-1.5">
                {adminNavItems.map((item) => (
                  <SidebarLink
                    key={item.path}
                    to={item.path}
                    label={t(item.labelKey)}
                    isActive={location.pathname === item.path || location.pathname.startsWith(`${item.path}/`)}
                  />
                ))}
              </div>
            </div>
          )}
        </nav>

        <div className="border-t border-slate-800/80 px-4 py-4">
          <div className="mb-4 rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-3">
            <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">
              Текущий tenant
            </div>
            <div className="mt-2 text-sm font-semibold text-slate-100">
              {activeWorkspace?.name || "Tenant не выбран"}
            </div>
            <div className="mt-1 text-xs text-slate-400">
              {activeWorkspace?.slug || "Выберите workspace для продолжения"}
            </div>
            {hasMultipleWorkspaces && (
              <button
                type="button"
                onClick={() => setWorkspaceModalOpen(true)}
                className="mt-3 text-sm font-medium text-cyan-300 transition hover:text-cyan-200"
              >
                Сменить tenant
              </button>
            )}
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-3">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">
                  {t("theme_toggle")}
                </div>
                <div className="mt-1 text-sm font-medium text-slate-200">
                  {theme === "dark" ? t("theme_dark") : t("theme_light")}
                </div>
              </div>
              <div className="rounded-full bg-slate-950/80 p-2 text-slate-200">
                {theme === "dark" ? <MoonIcon /> : <SunIcon />}
              </div>
            </div>
            <button
              type="button"
              onClick={toggleTheme}
              className="relative flex w-full items-center rounded-full bg-slate-800 px-2 py-1.5 text-left transition hover:bg-slate-700"
              aria-label={t("theme_toggle")}
              aria-pressed={theme === "dark"}
            >
              <span className="relative z-10 flex w-full items-center justify-between px-1 text-xs font-semibold uppercase tracking-[0.18em] text-slate-300">
                <span className="inline-flex items-center gap-1.5">
                  <SunIcon />
                  Light
                </span>
                <span className="inline-flex items-center gap-1.5">
                  Dark
                  <MoonIcon />
                </span>
              </span>
              <span
                className={[
                  "absolute top-1 h-[calc(100%-0.5rem)] w-[calc(50%-0.375rem)] rounded-full bg-cyan-400/90 shadow-lg shadow-cyan-900/30 transition-transform",
                  theme === "dark" ? "translate-x-[calc(100%+0.25rem)]" : "translate-x-0",
                ].join(" ")}
              />
            </button>
          </div>

          <div className="mt-4 rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-3">
            <div className="truncate text-sm font-semibold text-slate-100">{user?.email}</div>
            <button
              onClick={logout}
              className="mt-2 text-sm font-medium text-slate-300 transition hover:text-white"
            >
              {t("action_logout")}
            </button>
          </div>
        </div>
      </aside>

      <main className="flex-1 overflow-auto px-4 py-4 md:px-7 md:py-6">
        <div className="mb-4 flex items-center justify-end">
          <NotificationBell />
        </div>
        <Outlet />
      </main>

      <Modal
        isOpen={workspaceModalOpen}
        onClose={() => setWorkspaceModalOpen(false)}
        title="Выбор tenant"
      >
        <div className="space-y-3">
          <div className="text-sm text-slate-600 dark:text-slate-400">
            Выберите tenant/workspace, в котором хотите продолжить работу.
          </div>
          <div className="space-y-2">
            {workspaces.map((workspace) => {
              const isActiveWorkspace = workspace.id === workspacesResponse?.active_workspace_id;
              return (
                <button
                  key={workspace.id}
                  type="button"
                  onClick={() => switchMutation.mutate(workspace.id)}
                  className={[
                    "w-full rounded-xl border px-4 py-3 text-left transition",
                    isActiveWorkspace
                      ? "border-cyan-400 bg-cyan-50 text-slate-900 dark:border-cyan-500 dark:bg-slate-800"
                      : "border-slate-200 bg-white hover:border-cyan-300 dark:border-slate-700 dark:bg-slate-900",
                  ].join(" ")}
                  disabled={switchMutation.isPending}
                >
                  <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    {workspace.name}
                  </div>
                  <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                    {workspace.slug} • роль: {workspace.role}
                  </div>
                </button>
              );
          })}
          </div>
          {switchMutation.isError && (
            <ApiErrorNotice
              error={switchMutation.error}
              fallback="Не удалось переключить tenant"
              className="px-3 py-2"
            />
          )}
        </div>
      </Modal>
    </div>
  );
}
