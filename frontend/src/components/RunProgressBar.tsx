import React, { useEffect, useMemo, useState } from "react";

interface RunProgressBarProps {
  status: string;
  startedAt?: string | null;
  completedAt?: string | null;
  createdAt?: string | null;
  recordsProcessed?: number;
  sourceRecordsTotal?: number | null;
  sourceRecordsTotalIsEstimate?: boolean;
  tablesProcessed?: number;
  totalTables?: number;
}

function formatDuration(totalSeconds: number): string {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) return `${hours}ч ${minutes}м ${seconds}с`;
  if (minutes > 0) return `${minutes}м ${seconds}с`;
  return `${seconds}с`;
}

export function RunProgressBar({
  status,
  startedAt,
  completedAt,
  createdAt,
  recordsProcessed = 0,
  sourceRecordsTotal = null,
  sourceRecordsTotalIsEstimate = true,
  tablesProcessed = 0,
  totalTables,
}: RunProgressBarProps) {
  const isActive = status === "pending" || status === "running";
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!isActive) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [isActive]);

  const progress = useMemo(() => {
    if (status === "success") return 100;
    if (sourceRecordsTotal && sourceRecordsTotal > 0) {
      const ratio = Math.max(0, Math.min(1, recordsProcessed / sourceRecordsTotal));
      const ratioPercent = Math.round(ratio * 100);
      if (status === "failed" || status === "cancelled") return ratioPercent;
      if (status === "pending") return Math.max(2, Math.min(15, ratioPercent));
      if (status === "running") return Math.max(2, Math.min(99, ratioPercent));
      return ratioPercent;
    }
    if (status === "failed" || status === "cancelled") return 100;
    if (status === "pending") return 8;
    if (status === "running" && totalTables && totalTables > 0) {
      const ratio = Math.max(0, Math.min(1, tablesProcessed / totalTables));
      return Math.max(10, Math.min(95, Math.round(ratio * 100)));
    }
    return null;
  }, [status, recordsProcessed, sourceRecordsTotal, tablesProcessed, totalTables]);

  const toneClass =
    status === "success"
      ? "bg-emerald-500"
      : status === "failed"
        ? "bg-rose-500"
        : status === "cancelled"
          ? "bg-amber-500"
          : "bg-cyan-500";

  const start = startedAt ?? createdAt ?? null;
  const startMs = start ? Date.parse(start) : NaN;
  const endMs = completedAt ? Date.parse(completedAt) : now;
  const hasDuration = Number.isFinite(startMs) && Number.isFinite(endMs) && endMs >= startMs;
  const elapsedSeconds = hasDuration ? Math.floor((endMs - startMs) / 1000) : 0;

  return (
    <div className="mt-2 w-full">
      <div className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
        {progress === null ? (
          <div className="h-full w-2/5 animate-pulse rounded-full bg-cyan-500/80" />
        ) : (
          <div className={`h-full transition-all duration-500 ${toneClass}`} style={{ width: `${progress}%` }} />
        )}
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
        {sourceRecordsTotal && sourceRecordsTotal > 0 ? (
          <span>
            Записи: {Math.min(recordsProcessed, sourceRecordsTotal).toLocaleString()}/
            {sourceRecordsTotal.toLocaleString()}
            {sourceRecordsTotalIsEstimate ? " (оценка)" : ""}
          </span>
        ) : typeof totalTables === "number" && totalTables > 0 ? (
          <span>
            Таблицы: {Math.min(tablesProcessed, totalTables)}/{totalTables}
          </span>
        ) : (
          <span>
            {status === "pending" ? "Ожидание очереди" : status === "running" ? "Идет обработка данных" : "Завершено"}
          </span>
        )}
        {hasDuration && <span>Время: {formatDuration(elapsedSeconds)}</span>}
      </div>
    </div>
  );
}
