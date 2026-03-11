/**
 * Flows list page (T070).
 */

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import api from "../../services/api";
import { Button } from "../../components/common/Button";
import { Table } from "../../components/common/Table";
import { FlowStatusBadge } from "../../components/FlowStatusBadge";
import { Modal } from "../../components/common/Modal";
import { useToast } from "../../components/common/Toast";
import { useErrorToast } from "../../hooks/useErrorToast";
import { writeModeLabels } from "../../constants/labels";
import { useListWithPagination } from "../../hooks/useListWithPagination";

interface Flow {
  id: string;
  name: string;
  description?: string | null;
  status: string;
  source_id: string;
  target_schema: string;
  write_mode: string;
  [key: string]: unknown;
}

export default function FlowsList() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const { showErrorToast } = useErrorToast();
  const [deleteTarget, setDeleteTarget] = useState<Flow | null>(null);
  const [dropTargetTables, setDropTargetTables] = useState(false);
  const {
    items: flows,
    isLoading,
    page,
    hasNextPage,
    search,
    setPage,
    setSearch,
  } = useListWithPagination<Flow>({
    queryKey: ["flows"],
    endpoint: "/flows",
  });

  const deleteMutation = useMutation({
    mutationFn: (payload: { flowId: string; dropTargetTables: boolean }) =>
      api.delete(`/flows/${payload.flowId}`, {
        params: { drop_target_tables: payload.dropTargetTables },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["flows"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-flows"] });
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      addToast("success", "Поток удален");
      setDeleteTarget(null);
      setDropTargetTables(false);
    },
    onError: (error: unknown) => {
      showErrorToast(error, "Не удалось удалить поток");
    },
  });

  const columns = [
    { key: "name", header: "Название" },
    {
      key: "description",
      header: "Описание",
      render: (f: Flow) => f.description?.trim() || "—",
    },
    {
      key: "status",
      header: "Статус",
      render: (f: Flow) => <FlowStatusBadge status={f.status} />,
    },
    {
      key: "write_mode",
      header: "Режим",
      render: (f: Flow) => writeModeLabels[f.write_mode] || f.write_mode,
    },
    { key: "target_schema", header: "Цель" },
    {
      key: "actions",
      header: "Действия",
      render: (f: Flow) => (
        <div className="flex items-center gap-2">
          <Button
            variant="danger"
            className="px-2 py-1 text-xs"
            onClick={(e) => {
              e.stopPropagation();
              setDeleteTarget(f);
              setDropTargetTables(false);
            }}
          >
            Удалить
          </Button>
        </div>
      ),
    },
  ];

  const normalizedSearch = search.trim().toLowerCase();
  const filteredFlows = flows.filter((flow) => {
    if (!normalizedSearch) return true;
    return (
      flow.name.toLowerCase().includes(normalizedSearch) ||
      (flow.description || "").toLowerCase().includes(normalizedSearch) ||
      flow.status.toLowerCase().includes(normalizedSearch) ||
      flow.target_schema.toLowerCase().includes(normalizedSearch)
    );
  });

  if (isLoading) return <div>Загрузка...</div>;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Потоки</h1>
        <Button onClick={() => navigate("/flows/new")}>Создать поток</Button>
      </div>
      <div className="mb-4">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Поиск по имени, описанию, статусу или целевой схеме"
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:ring-2 focus:ring-cyan-500/70 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
      </div>

      <Table
        columns={columns}
        data={filteredFlows}
        onRowClick={(f) => navigate(`/flows/${f.id}`)}
        emptyMessage={normalizedSearch ? "Ничего не найдено" : "Потоки еще не созданы"}
      />
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
          Назад
        </Button>
        <Button
          variant="secondary"
          onClick={() => setPage((p) => p + 1)}
          disabled={!hasNextPage}
        >
          Далее
        </Button>
      </div>

      <Modal
        isOpen={deleteTarget !== null}
        onClose={() => {
          if (deleteMutation.isPending) return;
          setDeleteTarget(null);
          setDropTargetTables(false);
        }}
        title="Удаление потока"
      >
        <p className="mb-4 text-sm text-slate-700 dark:text-slate-300">
          Вы уверены, что хотите удалить поток <strong>{deleteTarget?.name}</strong>?
        </p>
        <p className="mb-4 text-xs text-amber-700 dark:text-amber-300">
          Внимание: действие необратимо. История запусков и настройки потока будут скрыты.
        </p>
        <label className="mb-4 flex items-start gap-2 text-sm text-slate-700 dark:text-slate-300">
          <input
            type="checkbox"
            checked={dropTargetTables}
            onChange={(e) => setDropTargetTables(e.target.checked)}
            className="mt-0.5"
          />
          <span>Также удалить целевые таблицы, созданные этим потоком, из business DB</span>
        </label>
        <div className="flex justify-end gap-2">
          <Button
            variant="secondary"
            onClick={() => {
              setDeleteTarget(null);
              setDropTargetTables(false);
            }}
            disabled={deleteMutation.isPending}
          >
            Отмена
          </Button>
          <Button
            variant="danger"
            loading={deleteMutation.isPending}
            onClick={() =>
              deleteTarget &&
              deleteMutation.mutate({
                flowId: deleteTarget.id,
                dropTargetTables,
              })
            }
          >
            Удалить
          </Button>
        </div>
      </Modal>
    </div>
  );
}
