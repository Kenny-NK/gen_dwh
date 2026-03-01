/**
 * Connection status indicator component (T047).
 */

import React from "react";

interface ConnectionStatusProps {
  status: string;
}

const statusConfig: Record<string, { color: string; label: string }> = {
  valid: { color: "bg-green-500", label: "Подключен" },
  invalid: { color: "bg-red-500", label: "Ошибка" },
  pending: { color: "bg-yellow-500", label: "Проверка" },
};

export function ConnectionStatus({ status }: ConnectionStatusProps) {
  const config = statusConfig[status] || statusConfig.pending;

  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-block h-2 w-2 rounded-full ${config.color}`} />
      <span className="text-sm text-slate-700 dark:text-slate-300">{config.label}</span>
    </span>
  );
}
