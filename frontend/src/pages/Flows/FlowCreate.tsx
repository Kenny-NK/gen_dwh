import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import api, { extractApiErrorMessage } from "../../services/api";
import { Button } from "../../components/common/Button";
import { Input } from "../../components/common/Input";
import { useToast } from "../../components/common/Toast";

type Source = {
  id: string;
  name: string;
  connection_status: string;
};

type FlowPayload = {
  name: string;
  source_id: string;
  target_schema: string;
  write_mode: "append" | "upsert" | "replace";
  description?: string;
  target_table_prefix?: string;
  upsert_key?: string;
};

const defaultPayload: FlowPayload = {
  name: "",
  source_id: "",
  target_schema: "public",
  write_mode: "append",
  description: "",
  target_table_prefix: "",
  upsert_key: "",
};

export default function FlowCreate() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const [payload, setPayload] = useState<FlowPayload>(defaultPayload);

  const { data: sources = [] } = useQuery<Source[]>({
    queryKey: ["sources", "valid-for-flow"],
    queryFn: () => api.get("/sources?status=valid").then((r) => r.data),
  });

  const createFlow = useMutation({
    mutationFn: async () => {
      const body: Record<string, unknown> = {
        ...payload,
      };
      if (!payload.description) {
        delete body.description;
      }
      if (!payload.target_table_prefix) {
        delete body.target_table_prefix;
      }
      if (!payload.upsert_key) {
        delete body.upsert_key;
      }
      const response = await api.post("/flows", body);
      return response.data as { id: string };
    },
    onSuccess: (flow) => {
      addToast("success", "Поток создан");
      queryClient.invalidateQueries({ queryKey: ["flows"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-flows"] });
      navigate(`/flows/${flow.id}`);
    },
    onError: (error: unknown) => {
      addToast("error", extractApiErrorMessage(error, "Не удалось создать поток"));
    },
  });

  const hasValidSources = sources.length > 0;

  return (
    <div className="mx-auto max-w-2xl app-card p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Создание потока</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Выберите источник, целевую схему и режим записи.
        </p>
      </div>

      <div className="space-y-4">
        <Input
          label="Название потока"
          value={payload.name}
          onChange={(e) => setPayload((prev) => ({ ...prev, name: e.target.value }))}
          placeholder="например, sales_incremental"
          required
        />

        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Источник</label>
          <select
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-cyan-500/70 transition focus:ring-2 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            value={payload.source_id}
            onChange={(e) => setPayload((prev) => ({ ...prev, source_id: e.target.value }))}
            disabled={!hasValidSources}
          >
            <option value="">Выберите источник</option>
            {sources.map((source) => (
              <option key={source.id} value={source.id}>
                {source.name}
              </option>
            ))}
          </select>
          {!hasValidSources && (
            <span className="text-xs text-amber-600 dark:text-amber-400">
              Не найдено валидных источников. Сначала создайте и проверьте источник.
            </span>
          )}
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Input
            label="Целевая схема"
            value={payload.target_schema}
            onChange={(e) => setPayload((prev) => ({ ...prev, target_schema: e.target.value }))}
            required
          />

          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Режим записи</label>
            <select
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-cyan-500/70 transition focus:ring-2 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
              value={payload.write_mode}
              onChange={(e) =>
                setPayload((prev) => ({
                  ...prev,
                  write_mode: e.target.value as FlowPayload["write_mode"],
                }))
              }
            >
              <option value="append">Добавление</option>
              <option value="upsert">Обновление и вставка</option>
              <option value="replace">Перезапись</option>
            </select>
          </div>
        </div>

        {payload.write_mode === "upsert" && (
          <Input
            label="Ключ upsert"
            value={payload.upsert_key}
            onChange={(e) => setPayload((prev) => ({ ...prev, upsert_key: e.target.value }))}
            placeholder="например, id"
          />
        )}

        <Input
          label="Префикс таблиц"
          value={payload.target_table_prefix}
          onChange={(e) => setPayload((prev) => ({ ...prev, target_table_prefix: e.target.value }))}
          placeholder="необязательно"
        />

        <Input
          label="Описание"
          value={payload.description}
          onChange={(e) => setPayload((prev) => ({ ...prev, description: e.target.value }))}
          placeholder="необязательно"
        />

        <div className="flex items-center gap-3 pt-2">
          <Button
            onClick={() => createFlow.mutate()}
            loading={createFlow.isPending}
            disabled={!payload.name || !payload.source_id || !payload.target_schema}
          >
            Создать поток
          </Button>
          <Button variant="secondary" onClick={() => navigate("/flows")}>Отмена</Button>
        </div>
      </div>
    </div>
  );
}
