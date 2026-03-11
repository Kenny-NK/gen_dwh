/**
 * Flows list widget for dashboard (T108).
 */

import React from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import api, { extractItems } from "../../services/api";
import { FlowStatusBadge } from "../../components/FlowStatusBadge";

type FlowSummary = {
  id: string;
  name: string;
  status: string;
};

export function FlowsWidget() {
  const navigate = useNavigate();

  const { data: flows = [] } = useQuery<FlowSummary[]>({
    queryKey: ["dashboard-flows"],
    queryFn: () => api.get("/flows").then((r) => extractItems<FlowSummary>(r.data)),
  });

  return (
    <div className="app-card p-4">
      <h2 className="mb-4 text-lg font-semibold text-slate-900 dark:text-slate-100">Потоки</h2>
      <div className="space-y-2">
        {flows.slice(0, 5).map((f) => (
          <div
            key={String(f.id)}
            className="flex cursor-pointer items-center justify-between rounded-lg p-2 transition hover:bg-slate-50 dark:hover:bg-slate-800"
            onClick={() => navigate(`/flows/${f.id}`)}
          >
            <span className="font-medium text-slate-800 dark:text-slate-200">{String(f.name)}</span>
            <FlowStatusBadge status={String(f.status)} />
          </div>
        ))}
        {flows.length === 0 && (
          <p className="text-sm text-slate-500 dark:text-slate-400">Потоков пока нет</p>
        )}
      </div>
    </div>
  );
}
