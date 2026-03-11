/**
 * Run status component with progress (T094).
 */

import React from "react";
import { getRunStatusUiConfig } from "../constants/runStatus";
import { formatCompactNumberRu } from "../utils/numberFormat";

interface RunStatusProps {
  status: string;
  recordsProcessed?: number;
  recordsFailed?: number;
}

export function RunStatus({ status, recordsProcessed, recordsFailed }: RunStatusProps) {
  const config = getRunStatusUiConfig(status);

  return (
    <div className="inline-flex max-w-full flex-wrap items-center gap-2">
      <span className={`rounded-full px-2 py-1 text-xs font-medium ${config.badgeClassName}`}>
        {config.label}
      </span>
      {status !== "running" && recordsProcessed !== undefined && recordsProcessed > 0 && (
        <span className="min-w-0 break-words text-xs text-slate-500 dark:text-slate-400">
          {formatCompactNumberRu(recordsProcessed)} записей
          {recordsFailed ? ` (${formatCompactNumberRu(recordsFailed)} с ошибкой)` : ""}
        </span>
      )}
    </div>
  );
}
