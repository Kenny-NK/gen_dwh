/**
 * Flow detail/edit page (T071).
 */

import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { extractApiErrorMessage, extractItems } from "../../services/api";
import { Button } from "../../components/common/Button";
import { Modal } from "../../components/common/Modal";
import { Preview } from "../../components/Preview/Preview";
import { useToast } from "../../components/common/Toast";
import { useErrorToast } from "../../hooks/useErrorToast";
import { writeModeLabels } from "../../constants/labels";

interface FlowData {
  id: string;
  name: string;
  description: string | null;
  source_id: string;
  target_schema: string;
  write_mode: string;
  status: string;
  status_reason?: string | null;
}

interface FlowTableData {
  id: string;
  source_schema: string;
  source_table: string;
  target_table: string;
  replication_method: string;
  replication_key: string | null;
}

interface RunData {
  id: string;
}

interface SourceTableData {
  name: string;
  row_count: number;
  columns: { name: string; data_type: string }[];
}

const statusLabels: Record<string, string> = {
  draft: "Черновик",
  paused: "Пауза",
  running: "Выполняется",
  success: "Успешно",
  failed: "Ошибка",
};

export default function FlowDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const { showErrorToast, getErrorMessage } = useErrorToast();
  const [previewSession, setPreviewSession] = useState<string | null>(null);
  const [selectedSchema, setSelectedSchema] = useState("");
  const [selectedSourceTable, setSelectedSourceTable] = useState("");
  const [deleteFlowOpen, setDeleteFlowOpen] = useState(false);
  const [dropFlowTargetTables, setDropFlowTargetTables] = useState(false);
  const [tableToDelete, setTableToDelete] = useState<FlowTableData | null>(null);
  const [dropSingleTargetTable, setDropSingleTargetTable] = useState(false);
  const selectedTableKey = selectedSchema && selectedSourceTable ? `${selectedSchema}.${selectedSourceTable}` : "";

  const { data: flow, isLoading } = useQuery<FlowData>({
    queryKey: ["flow", id],
    queryFn: ({ signal }) => api.get(`/flows/${id}`, { signal }).then((r) => r.data),
    enabled: !!id,
  });

  const { data: tables = [] } = useQuery<FlowTableData[]>({
    queryKey: ["flow-tables", id],
    queryFn: ({ signal }) =>
      api.get(`/flows/${id}/tables`, { signal }).then((r) => extractItems<FlowTableData>(r.data)),
    enabled: !!id,
  });

  const {
    data: sourceSchemas = [],
    isLoading: sourceSchemasLoading,
    error: sourceSchemasError,
  } = useQuery<string[]>({
    queryKey: ["flow-source-schemas", flow?.source_id],
    queryFn: ({ signal }) =>
      api.get(`/sources/${flow?.source_id}/schemas`, { signal }).then((r) => {
        const payload = r.data;
        return Array.isArray(payload?.schemas) ? payload.schemas : [];
      }),
    enabled: !!flow?.source_id,
  });

  const {
    data: sourceTables = [],
    isLoading: sourceTablesLoading,
    error: sourceTablesError,
  } = useQuery<SourceTableData[]>({
    queryKey: ["flow-source-tables", flow?.source_id, selectedSchema],
    queryFn: ({ signal }) =>
      api.get(`/sources/${flow?.source_id}/schemas/${selectedSchema}/tables`, { signal }).then((r) => {
        const payload = r.data;
        return Array.isArray(payload?.tables) ? payload.tables : [];
      }),
    enabled: !!flow?.source_id && !!selectedSchema,
  });

  useEffect(() => {
    if (sourceSchemas.length === 0) {
      setSelectedSchema("");
      return;
    }
    setSelectedSchema((current) => (current && sourceSchemas.includes(current) ? current : sourceSchemas[0]));
  }, [sourceSchemas]);

  useEffect(() => {
    if (!selectedSchema || sourceTables.length === 0) {
      setSelectedSourceTable("");
      return;
    }
    setSelectedSourceTable((current) =>
      current && sourceTables.some((table) => table.name === current) ? current : sourceTables[0].name
    );
  }, [selectedSchema, sourceTables]);

  const activateMutation = useMutation({
    mutationFn: () => api.post(`/flows/${id}/activate`),
    onSuccess: () => {
      addToast("success", "Поток активирован");
      queryClient.invalidateQueries({ queryKey: ["flow", id] });
      queryClient.invalidateQueries({ queryKey: ["flows"] });
    },
    onError: (error: unknown) => {
      showErrorToast(error, "Не удалось активировать поток");
    },
  });

  const pauseMutation = useMutation({
    mutationFn: () => api.post(`/flows/${id}/pause`),
    onSuccess: () => {
      addToast("success", "Поток поставлен на паузу");
      queryClient.invalidateQueries({ queryKey: ["flow", id] });
      queryClient.invalidateQueries({ queryKey: ["flows"] });
    },
    onError: (error: unknown) => {
      showErrorToast(error, "Не удалось поставить поток на паузу");
    },
  });

  const runMutation = useMutation({
    mutationFn: () => api.post(`/flows/${id}/runs`).then((r) => r.data as RunData),
    onSuccess: (data) => {
      addToast("success", "Запуск потока создан");
      queryClient.invalidateQueries({ queryKey: ["flow", id] });
      queryClient.invalidateQueries({ queryKey: ["flows"] });
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      navigate(`/runs/${data.id}`);
    },
    onError: (error: unknown) => {
      showErrorToast(error, "Не удалось запустить поток");
    },
  });

  const previewMutation = useMutation({
    mutationFn: () =>
      api
        .post(`/flows/${id}/preview`, {
          row_limit: 100,
          tables: tables.map((t) => `${t.source_schema}.${t.source_table}`),
        })
        .then((r) => r.data),
    onSuccess: (data) => {
      setPreviewSession(data.id);
      addToast("success", "Предпросмотр подготовлен");
    },
    onError: (error: unknown) => {
      showErrorToast(error, "Не удалось запустить предпросмотр");
    },
  });

  const addTableMutation = useMutation({
    mutationFn: () =>
      api.post(`/flows/${id}/tables`, {
        source_schema: selectedSchema,
        source_table: selectedSourceTable,
      }),
    onSuccess: () => {
      addToast("success", "Таблица добавлена в поток");
      queryClient.invalidateQueries({ queryKey: ["flow-tables", id] });
    },
    onError: (error: unknown) => {
      showErrorToast(error, "Не удалось добавить таблицу");
    },
  });

  const removeTableMutation = useMutation({
    mutationFn: (payload: { tableId: string; dropTargetTable: boolean }) =>
      api.delete(`/flows/${id}/tables/${payload.tableId}`, {
        params: { drop_target_table: payload.dropTargetTable },
      }),
    onSuccess: () => {
      addToast("success", "Таблица удалена из потока");
      queryClient.invalidateQueries({ queryKey: ["flow-tables", id] });
      setTableToDelete(null);
      setDropSingleTargetTable(false);
    },
    onError: (error: unknown) => {
      showErrorToast(error, "Не удалось удалить таблицу");
    },
  });

  const deleteFlowMutation = useMutation({
    mutationFn: (dropTargetTables: boolean) =>
      api.delete(`/flows/${id}`, {
        params: { drop_target_tables: dropTargetTables },
      }),
    onSuccess: () => {
      addToast("success", "Поток удален");
      queryClient.invalidateQueries({ queryKey: ["flows"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-flows"] });
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      navigate("/flows");
    },
    onError: (error: unknown) => {
      showErrorToast(error, "Не удалось удалить поток");
    },
  });

  if (isLoading) return <div>Загрузка...</div>;
  if (!flow) return <div>Поток не найден</div>;

  const alreadyAdded = tables.some(
    (t) => `${t.source_schema}.${t.source_table}` === selectedTableKey
  );
  const sourceSchemasErrorMessage = sourceSchemasError
    ? getErrorMessage(sourceSchemasError, "Не удалось получить список схем источника")
    : "";
  const sourceTablesErrorMessage = sourceTablesError
    ? extractApiErrorMessage(sourceTablesError, `Не удалось получить таблицы схемы ${selectedSchema}`)
    : "";

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">{flow.name}</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">{flow.description}</p>
        </div>
        <div className="flex gap-2">
          {flow.status === "draft" && (
            <Button onClick={() => activateMutation.mutate()} loading={activateMutation.isPending}>Активировать</Button>
          )}
          {["paused", "success", "failed"].includes(flow.status) && (
            <Button onClick={() => runMutation.mutate()} loading={runMutation.isPending} disabled={!tables.length}>
              Запустить
            </Button>
          )}
          {["success", "failed"].includes(flow.status) && (
            <Button variant="secondary" onClick={() => pauseMutation.mutate()} loading={pauseMutation.isPending}>
              Пауза
            </Button>
          )}
          <Button
            variant="secondary"
            onClick={() => previewMutation.mutate()}
            loading={previewMutation.isPending}
            disabled={!tables.length}
          >
            Предпросмотр
          </Button>
          <Button variant="secondary" onClick={() => navigate(`/flows/${id}/runs`)}>
            История запусков
          </Button>
          <Button
            variant="danger"
            onClick={() => {
              setDeleteFlowOpen(true);
              setDropFlowTargetTables(false);
            }}
            disabled={flow.status === "running"}
          >
            Удалить поток
          </Button>
        </div>
      </div>

      {/* Flow details */}
      <div className="mb-6 grid grid-cols-1 gap-4 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900 md:grid-cols-3">
        <div>
          <span className="text-sm text-slate-500 dark:text-slate-400">Статус</span>
          <div className="font-medium text-slate-900 dark:text-slate-100">{statusLabels[flow.status] || flow.status}</div>
          {flow.status_reason && (
            <div className="mt-1 text-xs text-amber-600 dark:text-amber-300">{flow.status_reason}</div>
          )}
        </div>
        <div>
          <span className="text-sm text-slate-500 dark:text-slate-400">Режим записи</span>
          <div className="font-medium text-slate-900 dark:text-slate-100">{writeModeLabels[flow.write_mode] || flow.write_mode}</div>
        </div>
        <div>
          <span className="text-sm text-slate-500 dark:text-slate-400">Целевая схема</span>
          <div className="font-medium text-slate-900 dark:text-slate-100">{flow.target_schema}</div>
        </div>
      </div>

      {/* Add table from source */}
      <div className="mb-6 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <h2 className="mb-3 text-lg font-semibold text-slate-900 dark:text-slate-100">Добавить таблицу из источника</h2>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <select
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            value={selectedSchema}
            onChange={(e) => {
              setSelectedSchema(e.target.value);
              setSelectedSourceTable("");
            }}
            disabled={sourceSchemasLoading || sourceSchemas.length === 0}
          >
            {sourceSchemasLoading && <option value="">Загрузка схем...</option>}
            {!sourceSchemasLoading && sourceSchemas.length === 0 && <option value="">Схемы не найдены</option>}
            {sourceSchemas.map((schema) => (
              <option key={schema} value={schema}>
                {schema}
              </option>
            ))}
          </select>
          <select
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            value={selectedSourceTable}
            onChange={(e) => setSelectedSourceTable(e.target.value)}
            disabled={!selectedSchema || sourceTablesLoading || sourceTables.length === 0}
          >
            <option value="">
              {!selectedSchema
                ? "Сначала выберите схему"
                : sourceTablesLoading
                  ? "Загрузка таблиц..."
                  : sourceTables.length === 0
                    ? "Таблицы не найдены"
                    : "Выберите таблицу"}
            </option>
            {sourceTables.map((table) => (
              <option key={table.name} value={table.name}>
                {table.name} ({table.row_count})
              </option>
            ))}
          </select>
          <Button
            onClick={() => addTableMutation.mutate()}
            loading={addTableMutation.isPending}
            disabled={!selectedSchema || !selectedSourceTable || alreadyAdded}
          >
            {alreadyAdded ? "Уже добавлена" : "Добавить"}
          </Button>
        </div>
        {sourceSchemasErrorMessage && (
          <p className="mt-3 text-sm text-rose-600 dark:text-rose-400">{sourceSchemasErrorMessage}</p>
        )}
        {sourceTablesErrorMessage && (
          <p className="mt-3 text-sm text-rose-600 dark:text-rose-400">{sourceTablesErrorMessage}</p>
        )}
        {sourceSchemas.length === 0 && (
          <p className="mt-3 text-sm text-amber-600 dark:text-amber-400">
            Для этого источника не найдено схем с доступными таблицами или объектами.
          </p>
        )}
        {!!selectedSchema && !sourceTablesLoading && !sourceTablesErrorMessage && sourceTables.length === 0 && (
          <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">
            В схеме <span className="font-medium">{selectedSchema}</span> нет доступных таблиц или файлов для добавления в поток.
          </p>
        )}
      </div>

      {/* Tables */}
      <h2 className="mb-4 text-lg font-semibold text-slate-900 dark:text-slate-100">Таблицы ({tables.length})</h2>
      <div className="mb-6 space-y-2">
        {tables.map((t) => (
          <div key={t.id} className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
            <div className="font-medium text-slate-900 dark:text-slate-100">
              {t.source_schema}.{t.source_table}
            </div>
            <div className="text-sm text-slate-500 dark:text-slate-400">
              Целевая таблица: {flow.target_schema}.{t.target_table}
            </div>
            <div className="text-sm text-slate-500 dark:text-slate-400">
              Метод: {t.replication_method}
              {Boolean(t.replication_key) && ` | Курсор: ${t.replication_key}`}
            </div>
            <div className="mt-2">
              <Button
                variant="danger"
                size="sm"
                onClick={() => {
                  setTableToDelete(t);
                  setDropSingleTargetTable(false);
                }}
                disabled={flow.status === "running"}
              >
                Удалить таблицу из потока
              </Button>
            </div>
          </div>
        ))}
        {!tables.length && (
          <div className="text-sm text-slate-500 dark:text-slate-400">Пока нет добавленных таблиц.</div>
        )}
      </div>

      {/* Preview */}
      {previewSession && (
        <div className="mt-6">
          <h2 className="mb-4 text-lg font-semibold text-slate-900 dark:text-slate-100">Предпросмотр</h2>
          <Preview
            flowId={id!}
            sessionId={previewSession}
            tables={tables.map((t) => `${t.source_schema}.${t.source_table}`)}
          />
        </div>
      )}

      <Modal
        isOpen={deleteFlowOpen}
        onClose={() => {
          if (deleteFlowMutation.isPending) return;
          setDeleteFlowOpen(false);
          setDropFlowTargetTables(false);
        }}
        title="Удаление потока"
      >
        <p className="mb-4 text-sm text-slate-700 dark:text-slate-300">
          Вы уверены, что хотите удалить поток <strong>{flow.name}</strong>?
        </p>
        <p className="mb-4 text-xs text-amber-700 dark:text-amber-300">
          Внимание: действие необратимо. Поток и привязанные таблицы будут удалены из конфигурации.
        </p>
        <label className="mb-4 flex items-start gap-2 text-sm text-slate-700 dark:text-slate-300">
          <input
            type="checkbox"
            checked={dropFlowTargetTables}
            onChange={(e) => setDropFlowTargetTables(e.target.checked)}
            className="mt-0.5"
          />
          <span>Также удалить все целевые таблицы этого потока из business DB</span>
        </label>
        <div className="flex justify-end gap-2">
          <Button
            variant="secondary"
            onClick={() => {
              setDeleteFlowOpen(false);
              setDropFlowTargetTables(false);
            }}
            disabled={deleteFlowMutation.isPending}
          >
            Отмена
          </Button>
          <Button
            variant="danger"
            loading={deleteFlowMutation.isPending}
            onClick={() => deleteFlowMutation.mutate(dropFlowTargetTables)}
          >
            Удалить поток
          </Button>
        </div>
      </Modal>

      <Modal
        isOpen={tableToDelete !== null}
        onClose={() => {
          if (removeTableMutation.isPending) return;
          setTableToDelete(null);
          setDropSingleTargetTable(false);
        }}
        title="Удаление таблицы из потока"
      >
        <p className="mb-4 text-sm text-slate-700 dark:text-slate-300">
          Удалить таблицу <strong>{tableToDelete?.source_schema}.{tableToDelete?.source_table}</strong> из потока?
        </p>
        <p className="mb-4 text-xs text-amber-700 dark:text-amber-300">
          Внимание: при удалении таблицы из потока новые загрузки по ней выполняться не будут.
        </p>
        <label className="mb-4 flex items-start gap-2 text-sm text-slate-700 dark:text-slate-300">
          <input
            type="checkbox"
            checked={dropSingleTargetTable}
            onChange={(e) => setDropSingleTargetTable(e.target.checked)}
            className="mt-0.5"
          />
          <span>
            Также удалить физическую таблицу {flow.target_schema}.{tableToDelete?.target_table} из business DB
          </span>
        </label>
        <div className="flex justify-end gap-2">
          <Button
            variant="secondary"
            onClick={() => {
              setTableToDelete(null);
              setDropSingleTargetTable(false);
            }}
            disabled={removeTableMutation.isPending}
          >
            Отмена
          </Button>
          <Button
            variant="danger"
            loading={removeTableMutation.isPending}
            onClick={() =>
              tableToDelete &&
              removeTableMutation.mutate({
                tableId: tableToDelete.id,
                dropTargetTable: dropSingleTargetTable,
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
