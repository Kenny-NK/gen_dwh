/**
 * Runs history page (T095).
 */

import React, { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import api from "../../services/api";
import { Table } from "../../components/common/Table";
import { RunStatus } from "../../components/RunStatus";

interface Run {
  id: string;
  flow_id: string;
  run_number: number;
  triggered_by: string;
  status: string;
  records_processed: number;
  created_at: string;
  [key: string]: unknown;
}

const triggerLabels: Record<string, string> = {
  manual: "Вручную",
  retry: "Повтор",
  scheduled: "По расписанию",
};

export default function RunsList() {
  const navigate = useNavigate();
  const { id: flowId } = useParams();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const { data: runs = [], isLoading } = useQuery<Run[]>({
    queryKey: ["runs", flowId ?? "all", page],
    queryFn: () =>
      api
        .get(flowId ? `/flows/${flowId}/runs` : "/runs", {
          params: { limit: pageSize, offset: (page - 1) * pageSize },
        })
        .then((r) => r.data),
  });

  const columns = [
    { key: "run_number", header: "#" },
    {
      key: "triggered_by",
      header: "Тип запуска",
      render: (r: Run) => triggerLabels[r.triggered_by] || r.triggered_by,
    },
    {
      key: "status",
      header: "Статус",
      render: (r: Run) => <RunStatus status={r.status} recordsProcessed={r.records_processed} />,
    },
    {
      key: "created_at",
      header: "Создан",
      render: (r: Run) => new Date(r.created_at).toLocaleString(),
    },
  ];

  const normalizedSearch = search.trim().toLowerCase();
  const filteredRuns = runs.filter((run) => {
    if (!normalizedSearch) return true;
    return (
      run.status.toLowerCase().includes(normalizedSearch) ||
      run.triggered_by.toLowerCase().includes(normalizedSearch) ||
      String(run.run_number).includes(normalizedSearch)
    );
  });

  if (isLoading) return <div>Загрузка...</div>;

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold text-slate-900 dark:text-slate-100">
        {flowId ? "История запусков потока" : "История запусков"}
      </h1>
      <div className="mb-4">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Поиск по номеру, статусу или типу запуска"
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:ring-2 focus:ring-cyan-500/70 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
      </div>
      <Table
        columns={columns}
        data={filteredRuns}
        onRowClick={(r) => navigate(`/runs/${r.id}`)}
        emptyMessage={normalizedSearch ? "Ничего не найдено" : "Запусков пока нет"}
      />
      <div className="mt-4 flex justify-end gap-2">
        <button
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300"
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          disabled={page === 1}
        >
          Назад
        </button>
        <button
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300"
          onClick={() => setPage((p) => p + 1)}
          disabled={runs.length < pageSize}
        >
          Далее
        </button>
      </div>
    </div>
  );
}
