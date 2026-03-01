/**
 * Layout component with navigation (T030).
 */

import React from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useTheme } from "../hooks/useTheme";
import { NotificationBell } from "./Notifications/NotificationBell";

const navItems = [
  { path: "/", label: "Панель" },
  { path: "/sources", label: "Источники" },
  { path: "/flows", label: "Потоки" },
  { path: "/runs", label: "Запуски" },
];

export function Layout() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="flex w-60 flex-col border-r border-slate-800/50 bg-slate-900/95 text-white">
        <div className="border-b border-slate-700/50 px-5 py-4">
          <h1 className="text-lg font-semibold tracking-wide">GenDWH</h1>
          <p className="mt-1 text-xs text-slate-400">Управление потоками данных</p>
        </div>
        <nav className="flex-1 space-y-1 p-3">
          {navItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              className={`block rounded-lg px-3 py-2 text-sm transition ${
                location.pathname === item.path
                  ? "bg-cyan-500/15 text-cyan-300"
                  : "text-slate-300 hover:bg-slate-800 hover:text-white"
              }`}
            >
              {item.label}
            </Link>
          ))}
          {user?.role === "admin" && (
            <Link
              to="/audit"
              className={`block rounded-lg px-3 py-2 text-sm transition ${
                location.pathname === "/audit"
                  ? "bg-cyan-500/15 text-cyan-300"
                  : "text-slate-300 hover:bg-slate-800 hover:text-white"
              }`}
            >
              Аудит
            </Link>
          )}
        </nav>
        <div className="border-t border-slate-700/50 px-4 py-4">
          <div className="text-sm text-slate-400">{user?.email}</div>
          <button
            onClick={logout}
            className="mt-2 text-sm text-slate-300 transition hover:text-white"
          >
            Выйти
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto px-4 py-4 md:px-7 md:py-6">
        <div className="mb-4 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={toggleTheme}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 transition hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
          >
            {theme === "dark" ? "Светлая тема" : "Темная тема"}
          </button>
          <NotificationBell />
        </div>
        <Outlet />
      </main>
    </div>
  );
}
