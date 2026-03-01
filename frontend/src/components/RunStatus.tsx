/**
 * Run status component with progress (T094).
 */

import React from "react";

interface RunStatusProps {
  status: string;
  recordsProcessed?: number;
  recordsFailed?: number;
}

const statusConfig: Record<string, { color: string; label: string }> = {
  pending: { color: "bg-slate-200 text-slate-800 dark:bg-slate-700 dark:text-slate-200", label: "Ожидание" },
  running: { color: "bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-200", label: "Выполняется" },
  success: { color: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200", label: "Успешно" },
  failed: { color: "bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-200", label: "Ошибка" },
  cancelled: { color: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-200", label: "Отменен" },
};

export function RunStatus({ status, recordsProcessed, recordsFailed }: RunStatusProps) {
  const config = statusConfig[status] || statusConfig.pending;

  return (
    <div className="inline-flex items-center gap-2">
      <span className={`rounded-full px-2 py-1 text-xs font-medium ${config.color}`}>
        {config.label}
      </span>
      {recordsProcessed !== undefined && recordsProcessed > 0 && (
        <span className="text-xs text-slate-500 dark:text-slate-400">
          {recordsProcessed.toLocaleString()} записей
          {recordsFailed ? ` (${recordsFailed} с ошибкой)` : ""}
        </span>
      )}
    </div>
  );
}
