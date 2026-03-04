/**
 * Run detail page with logs (T096).
 */

import React from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { extractApiErrorMessage } from "../../services/api";
import { Button } from "../../components/common/Button";
import { RunStatus } from "../../components/RunStatus";
import { RunProgressBar } from "../../components/RunProgressBar";
import { useToast } from "../../components/common/Toast";

interface RunDetailResponse {
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
  records_failed: number;
  retry_count: number;
  error_message: string | null;
  created_at: string;
}

const triggerLabels: Record<string, string> = {
  manual: "Вручную",
  retry: "Повтор",
  scheduled: "По расписанию",
};

export default function RunDetail() {
  const { id } = useParams();
  const queryClient = useQueryClient();
  const { addToast } = useToast();

  const { data: run, isLoading } = useQuery<RunDetailResponse>({
    queryKey: ["run", id],
    queryFn: () => api.get(`/runs/${id}`).then((r) => r.data),
    enabled: !!id,
    refetchInterval: (query) => {
      const data = query.state.data as RunDetailResponse | undefined;
      return data && ["pending", "running"].includes(data.status) ? 4000 : false;
    },
  });

  const flowId = run?.flow_id as string | undefined;
  const { data: flowTables = [] } = useQuery<Array<{ id: string }>>({
    queryKey: ["flow-tables", flowId],
    queryFn: () => api.get(`/flows/${flowId}/tables`).then((r) => r.data),
    enabled: Boolean(flowId),
  });

  const cancelMutation = useMutation({
    mutationFn: () =>
      api.post(`/flows/${flowId}/runs/${id}/cancel`).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["run", id] });
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-runs"] });
      addToast("success", "Запуск отменен");
    },
    onError: (error: unknown) => {
      addToast("error", extractApiErrorMessage(error, "Не удалось отменить запуск"));
    },
  });

  const retryMutation = useMutation({
    mutationFn: () =>
      api.post(`/flows/${flowId}/runs/${id}/retry`).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["run", id] });
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-runs"] });
      addToast("success", "Запуск отправлен на повтор");
    },
    onError: (error: unknown) => {
      addToast("error", extractApiErrorMessage(error, "Не удалось повторить запуск"));
    },
  });

  if (isLoading) return <div>Загрузка...</div>;
  if (!run) return <div>Запуск не найден</div>;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Запуск #{run.run_number}</h1>
          <RunStatus
            status={run.status}
            recordsProcessed={run.records_processed}
            recordsFailed={run.records_failed}
          />
          <RunProgressBar
            status={run.status}
            startedAt={run.started_at}
            completedAt={run.completed_at}
            createdAt={run.created_at}
            recordsProcessed={run.records_processed}
            sourceRecordsTotal={run.source_records_total}
            sourceRecordsTotalIsEstimate={run.source_records_total_is_estimate}
            tablesProcessed={run.tables_processed}
            totalTables={flowTables.length}
          />
        </div>
        <div className="flex gap-2">
          {["pending", "running"].includes(run.status) && (
            <Button
              variant="danger"
              onClick={() => cancelMutation.mutate()}
              loading={cancelMutation.isPending}
            >
              Отменить
            </Button>
          )}
          {run.status === "failed" && (
            <Button onClick={() => retryMutation.mutate()} loading={retryMutation.isPending}>
              Повторить
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900 md:grid-cols-2">
        <div>
          <span className="text-sm text-slate-500 dark:text-slate-400">Тип запуска</span>
          <div className="font-medium text-slate-900 dark:text-slate-100">
            {triggerLabels[run.triggered_by] || run.triggered_by}
          </div>
        </div>
        <div>
          <span className="text-sm text-slate-500 dark:text-slate-400">Количество повторов</span>
          <div className="font-medium text-slate-900 dark:text-slate-100">{run.retry_count}</div>
        </div>
        <div>
          <span className="text-sm text-slate-500 dark:text-slate-400">Начат</span>
          <div className="font-medium text-slate-900 dark:text-slate-100">
            {run.started_at ? new Date(run.started_at).toLocaleString() : "—"}
          </div>
        </div>
        <div>
          <span className="text-sm text-slate-500 dark:text-slate-400">Завершен</span>
          <div className="font-medium text-slate-900 dark:text-slate-100">
            {run.completed_at ? new Date(run.completed_at).toLocaleString() : "—"}
          </div>
        </div>
        <div>
          <span className="text-sm text-slate-500 dark:text-slate-400">Обработано записей</span>
          <div className="font-medium text-slate-900 dark:text-slate-100">{run.records_processed?.toLocaleString() || 0}</div>
        </div>
        <div>
          <span className="text-sm text-slate-500 dark:text-slate-400">Записей с ошибкой</span>
          <div className="font-medium text-slate-900 dark:text-slate-100">{run.records_failed?.toLocaleString() || 0}</div>
        </div>
      </div>

      {run.error_message && (
        <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-4 dark:border-rose-900 dark:bg-rose-950/30">
          <h3 className="mb-2 font-medium text-rose-800 dark:text-rose-200">Ошибка</h3>
          <pre className="whitespace-pre-wrap text-sm text-rose-700 dark:text-rose-200">
            {run.error_message}
          </pre>
        </div>
      )}
    </div>
  );
}
