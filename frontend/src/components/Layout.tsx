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

const SIDEBAR_COLLAPSED_STORAGE_KEY = "gendwh.sidebar.collapsed";

type NavItem = {
  path: string;
  labelKey: string;
  icon: React.ReactNode;
};

function DashboardIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="3.5" width="7" height="4" rx="1.5" />
      <rect x="13.5" y="10.5" width="7" height="10" rx="1.5" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
    </svg>
  );
}

function SourcesIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
      <ellipse cx="12" cy="6" rx="7.5" ry="2.5" />
      <path d="M4.5 6v6c0 1.4 3.4 2.5 7.5 2.5s7.5-1.1 7.5-2.5V6" />
      <path d="M4.5 12v6c0 1.4 3.4 2.5 7.5 2.5s7.5-1.1 7.5-2.5v-6" />
    </svg>
  );
}

function FlowsIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="6" cy="6" r="2.5" />
      <circle cx="18" cy="12" r="2.5" />
      <circle cx="6" cy="18" r="2.5" />
      <path d="M8.5 6h4A3.5 3.5 0 0 1 16 9.5v0" />
      <path d="M8.5 18h4A3.5 3.5 0 0 0 16 14.5v0" />
    </svg>
  );
}

function RunsIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M5 4.5h14" />
      <path d="M7 4.5v5l5 3 5-3v-5" />
      <path d="M12 12.5v7" />
      <path d="M8 19.5h8" />
    </svg>
  );
}

function UsersIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="9" cy="8" r="3" />
      <path d="M4.5 18a4.5 4.5 0 0 1 9 0" />
      <circle cx="17" cy="9" r="2.5" />
      <path d="M14.5 18a3.5 3.5 0 0 1 5 0" />
    </svg>
  );
}

function AuditIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M7 4.5h8l3 3V19a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 6 19V6A1.5 1.5 0 0 1 7.5 4.5Z" />
      <path d="M15 4.5V8h3" />
      <path d="M9 11h6M9 14h6M9 17h4" />
    </svg>
  );
}

const primaryNavItems = [
  { path: "/", labelKey: "nav_dashboard", icon: <DashboardIcon /> },
  { path: "/sources", labelKey: "nav_sources", icon: <SourcesIcon /> },
  { path: "/flows", labelKey: "nav_flows", icon: <FlowsIcon /> },
  { path: "/runs", labelKey: "nav_runs", icon: <RunsIcon /> },
] satisfies NavItem[];

const adminNavItems = [
  { path: "/admin/users-roles", labelKey: "nav_users_roles", icon: <UsersIcon /> },
  { path: "/audit", labelKey: "nav_audit", icon: <AuditIcon /> },
] satisfies NavItem[];

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

function SidebarToggleIcon({ collapsed }: { collapsed: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d={collapsed ? "m9 6 6 6-6 6" : "m15 6-6 6 6 6"} />
    </svg>
  );
}

function SidebarLink({
  to,
  label,
  icon,
  isActive,
  collapsed,
}: {
  to: string;
  label: string;
  icon: React.ReactNode;
  isActive: boolean;
  collapsed: boolean;
}) {
  return (
    <Link
      to={to}
      title={collapsed ? label : undefined}
      aria-label={collapsed ? label : undefined}
      className={[
        "block rounded-xl px-3 py-2.5 text-sm font-medium tracking-[0.01em] transition",
        collapsed ? "text-center" : "",
        isActive
          ? "bg-cyan-400/15 text-cyan-200 shadow-[inset_0_0_0_1px_rgba(103,232,249,0.18)]"
          : "text-slate-200 hover:bg-slate-800/90 hover:text-white",
      ].join(" ")}
    >
      {collapsed ? <span className="inline-flex items-center justify-center">{icon}</span> : label}
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
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === "true";
  });
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

  React.useEffect(() => {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, String(sidebarCollapsed));
  }, [sidebarCollapsed]);

  return (
    <div className="flex h-screen overflow-hidden bg-transparent">
      <aside
        className={[
          "flex h-screen shrink-0 flex-col border-r border-slate-800/60 bg-slate-950/95 text-white transition-[width] duration-200",
          sidebarCollapsed ? "w-24" : "w-72",
        ].join(" ")}
      >
        <div className={["border-b border-slate-800/80 py-5", sidebarCollapsed ? "px-3" : "px-6"].join(" ")}>
          <div className="flex items-start justify-between gap-3">
            <div className={sidebarCollapsed ? "min-w-0 flex-1 text-center" : "min-w-0 flex-1"}>
              <div className="text-sm uppercase tracking-[0.2em] text-cyan-300/70">
                {sidebarCollapsed ? (
                  <span className="font-semibold">GD</span>
                ) : (
                  <>
                    <span className="font-medium text-cyan-200/80">Gen</span>
                    <span className="font-bold text-cyan-200">DWH</span>
                  </>
                )}
              </div>
            </div>
            <button
              type="button"
              onClick={() => setSidebarCollapsed((current) => !current)}
              className="rounded-xl border border-slate-800 bg-slate-900/80 p-2 text-slate-300 transition hover:border-slate-700 hover:text-white"
              aria-label={sidebarCollapsed ? "Развернуть боковое меню" : "Свернуть боковое меню"}
              title={sidebarCollapsed ? "Развернуть меню" : "Свернуть меню"}
            >
              <SidebarToggleIcon collapsed={sidebarCollapsed} />
            </button>
          </div>
        </div>

        <nav className={["flex-1 overflow-y-auto py-5", sidebarCollapsed ? "px-3" : "px-4"].join(" ")}>
          <div className="space-y-1.5">
            {primaryNavItems.map((item) => (
              <SidebarLink
                key={item.path}
                to={item.path}
                label={t(item.labelKey)}
                icon={item.icon}
                collapsed={sidebarCollapsed}
                isActive={location.pathname === item.path || location.pathname.startsWith(`${item.path}/`)}
              />
            ))}
          </div>

          {isAdmin && (
            <div className="mt-8">
              {!sidebarCollapsed && (
                <div className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">
                  Admin
                </div>
              )}
              <div className="space-y-1.5">
                {adminNavItems.map((item) => (
                  <SidebarLink
                    key={item.path}
                    to={item.path}
                    label={t(item.labelKey)}
                    icon={item.icon}
                    collapsed={sidebarCollapsed}
                    isActive={location.pathname === item.path || location.pathname.startsWith(`${item.path}/`)}
                  />
                ))}
              </div>
            </div>
          )}
        </nav>

        <div className={["border-t border-slate-800/80 py-4", sidebarCollapsed ? "px-3" : "px-4"].join(" ")}>
          <button
            type="button"
            onClick={toggleTheme}
            className={[
              "relative mb-4 inline-flex w-full items-center rounded-full border border-slate-800/80 bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.16),rgba(15,23,42,0.92)_65%)] p-1 text-left shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_12px_32px_rgba(2,6,23,0.35)] transition hover:border-slate-700 hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_16px_36px_rgba(2,6,23,0.45)]",
              sidebarCollapsed ? "justify-center" : "",
            ].join(" ")}
            aria-label={t("theme_toggle")}
            aria-pressed={theme === "dark"}
            title={t("theme_toggle")}
          >
            <span className="relative z-10 flex w-full items-center justify-between text-slate-300">
              <span className="inline-flex min-w-0 flex-1 items-center justify-center gap-2 px-3 py-1.5 text-xs font-semibold text-slate-100">
                <SunIcon />
                {!sidebarCollapsed && <span className="truncate">Светлая</span>}
              </span>
              <span className="inline-flex min-w-0 flex-1 items-center justify-center gap-2 px-3 py-1.5 text-xs font-semibold text-slate-100">
                <MoonIcon />
                {!sidebarCollapsed && <span className="truncate">Темная</span>}
              </span>
            </span>
            <span
              className={[
                "absolute top-1 h-[calc(100%-0.5rem)] rounded-full bg-cyan-400/90 shadow-[0_8px_18px_rgba(8,145,178,0.45)] transition-transform",
                sidebarCollapsed ? "w-[calc(100%-0.5rem)]" : "w-[calc(50%-0.375rem)]",
                theme === "dark"
                  ? sidebarCollapsed
                    ? "translate-x-0"
                    : "translate-x-[calc(100%+0.25rem)]"
                  : "translate-x-0",
              ].join(" ")}
            />
          </button>

          <div className={["mb-4 rounded-2xl border border-slate-800 bg-slate-900/70", sidebarCollapsed ? "px-3 py-3 text-center" : "px-4 py-3"].join(" ")}>
            {!sidebarCollapsed ? (
              <>
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
              </>
            ) : (
              <>
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                  Tenant
                </div>
                <button
                  type="button"
                  onClick={() => setWorkspaceModalOpen(true)}
                  className="mt-2 w-full rounded-xl bg-slate-800 px-2 py-2 text-xs font-semibold text-slate-100 transition hover:bg-slate-700"
                  title={activeWorkspace?.name || "Выбрать tenant"}
                >
                  {activeWorkspace?.slug || "—"}
                </button>
              </>
            )}
          </div>

          <div className={["mt-4 rounded-2xl border border-slate-800 bg-slate-900/70", sidebarCollapsed ? "px-3 py-3 text-center" : "px-4 py-3"].join(" ")}>
            {!sidebarCollapsed && <div className="truncate text-sm font-semibold text-slate-100">{user?.email}</div>}
            <button
              onClick={logout}
              className={[
                "text-sm font-medium text-slate-300 transition hover:text-white",
                sidebarCollapsed ? "" : "mt-2",
              ].join(" ")}
              title={sidebarCollapsed ? t("action_logout") : undefined}
            >
              {sidebarCollapsed ? "Выйти" : t("action_logout")}
            </button>
          </div>
        </div>
      </aside>

      <main className="flex h-screen min-h-0 flex-1 flex-col overflow-y-auto px-4 py-4 md:px-7 md:py-6">
        <div className="mb-4 flex items-center justify-end">
          <NotificationBell />
        </div>
        <div className="flex-1">
          <Outlet />
        </div>
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
