/**
 * Dashboard page with stats (T107, T115).
 */

import React from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import api from "../../services/api";
import { Button } from "../../components/common/Button";
import { FlowsWidget } from "./FlowsWidget";
import { SourcesWidget } from "./SourcesWidget";
import { RunsWidget } from "./RunsWidget";

export default function Dashboard() {
  const navigate = useNavigate();

  const { data: stats } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: () => api.get("/dashboard/stats").then((r) => r.data),
  });

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Панель управления</h1>
        <div className="flex gap-2">
          <Button onClick={() => navigate("/flows/new")}>Создать поток</Button>
          <Button variant="secondary" onClick={() => navigate("/sources/new")}>
            Подключить источник
          </Button>
        </div>
      </div>

      {/* Stats cards */}
      {stats && (
        <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="app-card p-4">
            <div className="text-sm text-slate-500 dark:text-slate-400">Источники</div>
            <div className="text-2xl font-bold text-slate-900 dark:text-slate-100">{stats.total_sources}</div>
          </div>
          <div className="app-card p-4">
            <div className="text-sm text-slate-500 dark:text-slate-400">Активные потоки</div>
            <div className="text-2xl font-bold text-slate-900 dark:text-slate-100">
              {(stats.flows_by_status?.running || 0) +
                (stats.flows_by_status?.paused || 0)}
            </div>
          </div>
          <div className="app-card p-4">
            <div className="text-sm text-slate-500 dark:text-slate-400">Успешные запуски</div>
            <div className="text-2xl font-bold text-green-600">
              {stats.runs_by_status?.success || 0}
            </div>
          </div>
          <div className="app-card p-4">
            <div className="text-sm text-slate-500 dark:text-slate-400">Обработано записей</div>
            <div className="text-2xl font-bold text-slate-900 dark:text-slate-100">
              {(stats.total_records_processed || 0).toLocaleString()}
            </div>
          </div>
        </div>
      )}

      {/* Widgets */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <FlowsWidget />
        <SourcesWidget />
      </div>
      <div className="mt-6">
        <RunsWidget />
      </div>
    </div>
  );
}
