import React from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";

import api, { extractApiErrorMessage } from "../../services/api";
import { Button } from "../../components/common/Button";
import { Input } from "../../components/common/Input";
import { useToast } from "../../components/common/Toast";

type Source = {
  id: string;
  name: string;
  source_type: "postgres" | "s3";
  connection_status: string;
};

const flowSchema = z
  .object({
    name: z.string().trim().min(1, "Название обязательно").max(255, "Максимум 255 символов"),
    source_id: z.string().trim().min(1, "Источник обязателен"),
    target_schema: z
      .string()
      .trim()
      .min(1, "Целевая схема обязательна")
      .max(63, "Максимум 63 символа"),
    write_mode: z.enum(["append", "upsert", "replace"]),
    description: z.string().optional().default(""),
    target_table_prefix: z.string().optional().default(""),
    upsert_key: z.string().optional().default(""),
  })
  .superRefine((value, ctx) => {
    if (value.write_mode === "upsert" && !value.upsert_key?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["upsert_key"],
        message: "Для режима upsert укажите ключ",
      });
    }
  });
type FlowPayload = z.infer<typeof flowSchema>;

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
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isValid },
  } = useForm<FlowPayload>({
    resolver: zodResolver(flowSchema),
    defaultValues: defaultPayload,
    mode: "onChange",
  });

  const { data: sources = [] } = useQuery<Source[]>({
    queryKey: ["sources", "valid-for-flow"],
    queryFn: () => api.get("/sources?status=valid").then((r) => r.data),
  });

  const createFlow = useMutation({
    mutationFn: async (payload: FlowPayload) => {
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
  const writeMode = watch("write_mode");

  return (
    <div className="mx-auto max-w-2xl app-card p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Создание потока</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Выберите источник, целевую схему и режим записи.
        </p>
      </div>

      <form className="space-y-4" onSubmit={handleSubmit((values) => createFlow.mutate(values))}>
        <Input
          label="Название потока"
          error={errors.name?.message}
          {...register("name")}
          placeholder="например, sales_incremental"
          required
        />

        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Источник</label>
          <select
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-cyan-500/70 transition focus:ring-2 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            {...register("source_id")}
            disabled={!hasValidSources}
          >
            <option value="">Выберите источник</option>
            {sources.map((source) => (
              <option key={source.id} value={source.id}>
                {source.name} ({source.source_type === "s3" ? "S3" : "PostgreSQL"})
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
            error={errors.target_schema?.message}
            {...register("target_schema")}
            required
          />

          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Режим записи</label>
            <select
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-cyan-500/70 transition focus:ring-2 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
              {...register("write_mode")}
            >
              <option value="append">Добавление</option>
              <option value="upsert">Обновление и вставка</option>
              <option value="replace">Перезапись</option>
            </select>
          </div>
        </div>

        {writeMode === "upsert" && (
          <Input
            label="Ключ upsert"
            error={errors.upsert_key?.message}
            {...register("upsert_key")}
            placeholder="например, id"
          />
        )}

        <Input
          label="Префикс таблиц"
          error={errors.target_table_prefix?.message}
          {...register("target_table_prefix")}
          placeholder="необязательно"
        />

        <Input
          label="Описание"
          error={errors.description?.message}
          {...register("description")}
          placeholder="необязательно"
        />

        <div className="flex items-center gap-3 pt-2">
          <Button
            type="submit"
            loading={createFlow.isPending}
            disabled={!isValid || !hasValidSources}
          >
            Создать поток
          </Button>
          <Button variant="secondary" onClick={() => navigate("/flows")}>Отмена</Button>
        </div>
      </form>
    </div>
  );
}
