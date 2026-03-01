/**
 * Flow status badges (T114).
 */

import React from "react";

interface FlowStatusBadgeProps {
  status: string;
}

const statusConfig: Record<string, { color: string; label: string }> = {
  draft: { color: "bg-slate-200 text-slate-800 dark:bg-slate-700 dark:text-slate-200", label: "Черновик" },
  paused: { color: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-200", label: "Пауза" },
  running: { color: "bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-200", label: "Выполняется" },
  success: { color: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200", label: "Успешно" },
  failed: { color: "bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-200", label: "Ошибка" },
};

export function FlowStatusBadge({ status }: FlowStatusBadgeProps) {
  const config = statusConfig[status] || statusConfig.draft;
  return (
    <span className={`rounded-full px-2 py-1 text-xs font-medium ${config.color}`}>
      {config.label}
    </span>
  );
}
