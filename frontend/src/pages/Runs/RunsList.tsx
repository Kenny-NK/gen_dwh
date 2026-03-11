/**
 * Runs history page (T095).
 */

import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { triggerLabels } from "../../constants/labels";
import { useListWithPagination } from "../../hooks/useListWithPagination";
import { Table } from "../../components/common/Table";
import { RunStatus } from "../../components/RunStatus";
import { RunProgressBar } from "../../components/RunProgressBar";
import { formatDateTime } from "../../utils/formatDate";

interface Run {
  id: string;
  flow_id: string;
  run_number: number;
  triggered_by: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  tables_processed: number;
  records_processed: number;
  source_records_total: number | null;
  source_records_total_is_estimate: boolean;
  created_at: string;
  [key: string]: unknown;
}

export default function RunsList() {
  const navigate = useNavigate();
  const { id: flowId } = useParams();
  const {
    items: runs,
    isLoading,
    page,
    hasNextPage,
    search,
    setPage,
    setSearch,
  } = useListWithPagination<Run>({
    queryKey: ["runs", flowId ?? "all"],
    endpoint: flowId ? `/flows/${flowId}/runs` : "/runs",
    refetchInterval: (items) =>
      items.some((run) => ["pending", "running"].includes(run.status)) ? 5000 : false,
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
      render: (r: Run) => (
        <div className="w-full min-w-[280px] max-w-[420px]">
          <RunStatus status={r.status} recordsProcessed={r.records_processed} />
          <RunProgressBar
            status={r.status}
            startedAt={r.started_at}
            completedAt={r.completed_at}
            createdAt={r.created_at}
            recordsProcessed={r.records_processed}
            sourceRecordsTotal={r.source_records_total}
            sourceRecordsTotalIsEstimate={r.source_records_total_is_estimate}
            tablesProcessed={r.tables_processed}
          />
        </div>
      ),
    },
    {
      key: "created_at",
      header: "Создан",
      render: (r: Run) => formatDateTime(r.created_at),
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
          disabled={!hasNextPage}
        >
          Далее
        </button>
      </div>
    </div>
  );
}
