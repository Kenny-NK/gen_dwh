import React, { useEffect, useMemo, useState } from "react";
import { getRunStatusUiConfig } from "../constants/runStatus";
import { formatCompactNumberRu } from "../utils/numberFormat";

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

  const statusConfig = getRunStatusUiConfig(status);

  const start = startedAt ?? createdAt ?? null;
  const startMs = start ? Date.parse(start) : NaN;
  const endMs = completedAt ? Date.parse(completedAt) : now;
  const hasDuration = Number.isFinite(startMs) && Number.isFinite(endMs) && endMs >= startMs;
  const elapsedSeconds = hasDuration ? Math.floor((endMs - startMs) / 1000) : 0;
  const processed = Math.max(0, recordsProcessed);
  const progressPercentByRecords = useMemo(() => {
    if (!sourceRecordsTotal || sourceRecordsTotal <= 0) return null;
    const ratio = processed / sourceRecordsTotal;
    if (!Number.isFinite(ratio) || ratio < 0) return 0;
    return Math.max(0, Math.round(ratio * 100));
  }, [processed, sourceRecordsTotal]);
  const ratePerSecond = useMemo(() => {
    if (!hasDuration || elapsedSeconds <= 0) return null;
    if (processed <= 0) return null;
    const rate = processed / elapsedSeconds;
    if (!Number.isFinite(rate) || rate <= 0) return null;
    return rate;
  }, [hasDuration, elapsedSeconds, processed]);
  const etaSeconds = useMemo(() => {
    if (!isActive) return null;
    if (!sourceRecordsTotal || sourceRecordsTotal <= 0) return null;
    if (!hasDuration || elapsedSeconds <= 0 || elapsedSeconds < 5) return null;
    if (processed <= 0 || processed < 1000) return null;
    if (sourceRecordsTotalIsEstimate && processed >= sourceRecordsTotal) return null;
    const remaining = Math.max(0, sourceRecordsTotal - processed);
    if (remaining <= 0) return 0;
    if (!ratePerSecond) return null;
    return Math.ceil(remaining / ratePerSecond);
  }, [
    isActive,
    sourceRecordsTotal,
    sourceRecordsTotalIsEstimate,
    hasDuration,
    elapsedSeconds,
    processed,
    ratePerSecond,
  ]);

  return (
    <div className="mt-2 w-full min-w-0 overflow-hidden">
      <div className="h-2 w-1/2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
        {progress === null ? (
          <div className="h-full w-2/5 animate-pulse rounded-full bg-cyan-500/80" />
        ) : (
          <div
            className={`h-full transition-all duration-500 ${statusConfig.progressToneClassName}`}
            style={{ width: `${progress}%` }}
          />
        )}
      </div>
      <div className="mt-1 flex w-full min-w-0 flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
        {sourceRecordsTotal && sourceRecordsTotal > 0 ? (
          <span className="min-w-0 break-words">
            Записи: {formatCompactNumberRu(processed)}/{formatCompactNumberRu(sourceRecordsTotal)}
            {sourceRecordsTotalIsEstimate ? " (оценка)" : ""}
          </span>
        ) : typeof totalTables === "number" && totalTables > 0 ? (
          <span className="min-w-0 break-words">
            Таблицы: {Math.min(tablesProcessed, totalTables)}/{totalTables}
          </span>
        ) : (
          <span className="min-w-0 break-words">
            {statusConfig.fallbackActivityLabel}
          </span>
        )}
        {progressPercentByRecords !== null && <span className="min-w-0 break-words">Прогресс: {progressPercentByRecords}%</span>}
        {hasDuration && <span className="min-w-0 break-words">Время: {formatDuration(elapsedSeconds)}</span>}
        {ratePerSecond !== null && (
          <span className="min-w-0 break-words">Скорость: ~{formatCompactNumberRu(Math.max(1, Math.round(ratePerSecond)))} зап/с</span>
        )}
        {etaSeconds !== null && <span className="min-w-0 break-words">Осталось: ~{formatDuration(etaSeconds)}</span>}
      </div>
    </div>
  );
}
