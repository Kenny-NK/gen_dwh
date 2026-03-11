/**
 * Sources list widget for dashboard (T109).
 */

import React from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import api, { extractItems } from "../../services/api";
import { ConnectionStatus } from "../../components/ConnectionStatus";

type SourceSummary = {
  id: string;
  name: string;
  host: string;
  database: string;
  connection_status: string;
};

export function SourcesWidget() {
  const navigate = useNavigate();

  const { data: sources = [] } = useQuery<SourceSummary[]>({
    queryKey: ["dashboard-sources"],
    queryFn: () => api.get("/sources").then((r) => extractItems<SourceSummary>(r.data)),
  });

  return (
    <div className="app-card p-4">
      <h2 className="mb-4 text-lg font-semibold text-slate-900 dark:text-slate-100">Источники</h2>
      <div className="space-y-2">
        {sources.slice(0, 5).map((s) => (
          <div
            key={String(s.id)}
            className="flex cursor-pointer items-center justify-between rounded-lg p-2 transition hover:bg-slate-50 dark:hover:bg-slate-800"
            onClick={() => navigate(`/sources/${s.id}/edit`)}
          >
            <div>
              <span className="font-medium text-slate-800 dark:text-slate-200">{String(s.name)}</span>
              <span className="ml-2 text-sm text-slate-500 dark:text-slate-400">
                {String(s.host)}/{String(s.database)}
              </span>
            </div>
            <ConnectionStatus status={String(s.connection_status)} />
          </div>
        ))}
        {sources.length === 0 && (
          <p className="text-sm text-slate-500 dark:text-slate-400">Источников пока нет</p>
        )}
      </div>
    </div>
  );
}
