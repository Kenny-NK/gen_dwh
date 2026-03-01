/**
 * Runs history widget for dashboard (T110).
 */

import React from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import api from "../../services/api";
import { RunStatus } from "../../components/RunStatus";

const triggerLabels: Record<string, string> = {
  manual: "вручную",
  retry: "повтор",
  scheduled: "по расписанию",
};

export function RunsWidget() {
  const navigate = useNavigate();

  const { data: runs = [] } = useQuery({
    queryKey: ["dashboard-runs"],
    queryFn: () => api.get("/runs?limit=10").then((r) => r.data),
  });

  return (
    <div className="app-card p-4">
      <h2 className="mb-4 text-lg font-semibold text-slate-900 dark:text-slate-100">Последние запуски</h2>
      <div className="space-y-2">
        {runs.slice(0, 10).map((r: Record<string, unknown>) => (
          <div
            key={String(r.id)}
            className="flex cursor-pointer items-center justify-between rounded-lg p-2 transition hover:bg-slate-50 dark:hover:bg-slate-800"
            onClick={() => navigate(`/runs/${r.id}`)}
          >
            <span className="text-sm text-slate-700 dark:text-slate-300">
              Запуск #{String(r.run_number)} - {triggerLabels[String(r.triggered_by)] || String(r.triggered_by)}
            </span>
            <div className="flex items-center gap-2">
              <RunStatus status={String(r.status)} />
              <span className="text-xs text-slate-400 dark:text-slate-500">
                {new Date(String(r.created_at)).toLocaleString()}
              </span>
            </div>
          </div>
        ))}
        {runs.length === 0 && (
          <p className="text-sm text-slate-500 dark:text-slate-400">Запусков пока нет</p>
        )}
      </div>
    </div>
  );
}
