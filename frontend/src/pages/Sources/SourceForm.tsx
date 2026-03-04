/**
 * Source form component - create/edit (T046, T048, T049).
 */

import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import api, { extractApiErrorMessage } from "../../services/api";
import { Button } from "../../components/common/Button";
import { Input } from "../../components/common/Input";
import { ConnectionStatus } from "../../components/ConnectionStatus";
import { useToast } from "../../components/common/Toast";

const sourceBaseSchema = z.object({
  name: z.string().trim().min(1, "Название обязательно").max(255, "Максимум 255 символов"),
  source_type: z.enum(["postgres", "s3"]),
  host: z.string().trim().min(1, "Хост обязателен").max(255, "Максимум 255 символов"),
  port: z.coerce.number().int().min(1, "Минимум 1").max(65535, "Максимум 65535"),
  database: z.string().trim().min(1, "База данных обязательна").max(255, "Максимум 255 символов"),
  username: z.string().trim().min(1, "Пользователь обязателен").max(255, "Максимум 255 символов"),
  password: z.string(),
  description: z.string().optional().default(""),
});
const sourceCreateSchema = sourceBaseSchema.refine((value) => value.password.trim().length > 0, {
  path: ["password"],
  message: "Пароль обязателен",
});
const sourceEditSchema = sourceBaseSchema;
type SourceFormData = z.infer<typeof sourceBaseSchema>;

interface SourceResponse {
  name: string;
  source_type: "postgres" | "s3";
  host: string;
  port: number;
  database: string;
  username: string;
  description?: string | null;
}

interface SourceTestResponse {
  success: boolean;
  message: string;
}

const SOURCE_FORM_DRAFT_KEY = "source-form-draft-v1";

const defaultForm: SourceFormData = {
  name: "",
  source_type: "postgres",
  host: "",
  port: 5432,
  database: "",
  username: "",
  password: "",
  description: "",
};

export default function SourceForm() {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isEditing = !!id;
  const schema = useMemo(() => (isEditing ? sourceEditSchema : sourceCreateSchema), [isEditing]);

  const [testResult, setTestResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);
  const { addToast } = useToast();
  const {
    register,
    handleSubmit,
    reset,
    setValue,
    getValues,
    watch,
    formState: { errors },
  } = useForm<SourceFormData>({
    resolver: zodResolver(schema),
    defaultValues: defaultForm,
  });
  const sourceType = watch("source_type");

  const getErrorMessage = (error: unknown): string => {
    return extractApiErrorMessage(error, "Ошибка запроса. Проверьте параметры и попробуйте снова.");
  };

  const {
    data: source,
    isError: isSourceError,
    error: sourceError,
  } = useQuery<SourceResponse>({
    queryKey: ["source", id],
    queryFn: () => api.get(`/sources/${id}`).then((r) => r.data),
    enabled: isEditing,
    retry: false,
  });

  useEffect(() => {
    if (isSourceError) {
      addToast("error", getErrorMessage(sourceError));
    }
  }, [isSourceError, sourceError, addToast]);

  useEffect(() => {
    if (source) {
      reset({
        name: source.name,
        source_type: source.source_type || "postgres",
        host: source.host,
        port: source.port,
        database: source.database,
        username: source.username,
        password: "",
        description: source.description || "",
      });
    }
  }, [source, reset]);

  useEffect(() => {
    if (isEditing) return;
    const raw = window.sessionStorage.getItem(SOURCE_FORM_DRAFT_KEY);
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw) as Partial<SourceFormData>;
      reset({
        ...defaultForm,
        ...parsed,
        password: "",
      });
    } catch {
      window.sessionStorage.removeItem(SOURCE_FORM_DRAFT_KEY);
    }
  }, [isEditing, reset]);

  useEffect(() => {
    if (isEditing) return;
    const subscription = watch((values) => {
      const draft = {
        ...values,
        password: "",
      };
      window.sessionStorage.setItem(SOURCE_FORM_DRAFT_KEY, JSON.stringify(draft));
    });
    return () => subscription.unsubscribe();
  }, [isEditing, watch]);

  useEffect(() => {
    if (isEditing) return;
    if (sourceType !== "s3") return;
    const currentHost = getValues("host");
    const currentPort = getValues("port");
    if (!currentHost) {
      setValue("host", "s3.amazonaws.com", { shouldValidate: true });
    }
    if (!currentPort || currentPort === 5432) {
      setValue("port", 443, { shouldValidate: true });
    }
  }, [getValues, isEditing, setValue, sourceType]);

  const saveMutation = useMutation({
    mutationFn: (data: SourceFormData) =>
      isEditing
        ? api.patch(`/sources/${id}`, {
            ...data,
            password: data.password.trim() || undefined,
          })
        : api.post("/sources", data),
    onSuccess: () => {
      if (!isEditing) {
        window.sessionStorage.removeItem(SOURCE_FORM_DRAFT_KEY);
      }
      addToast("success", isEditing ? "Источник обновлен" : "Источник создан");
      queryClient.invalidateQueries({ queryKey: ["sources"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-sources"] });
      navigate("/sources");
    },
    onError: (error) => {
      addToast("error", getErrorMessage(error));
    },
  });

  const testMutation = useMutation({
    mutationFn: () => api.post(`/sources/${id}/test`).then((r) => r.data),
    onSuccess: (data: SourceTestResponse) => {
      setTestResult(data);
      addToast("info", data.success ? "Подключение успешно" : data.message);
    },
    onError: (error) => {
      addToast("error", getErrorMessage(error));
    },
  });

  const name = watch("name");
  const host = watch("host");
  const database = watch("database");
  const username = watch("username");
  const sourceId = id;

  return (
    <div className="mx-auto max-w-xl app-card p-6">
      <h1 className="mb-6 text-2xl font-bold text-slate-900 dark:text-slate-100">
        {isEditing ? "Редактирование источника" : "Новый источник"}
      </h1>

      <form className="space-y-4" onSubmit={handleSubmit((values) => saveMutation.mutate(values))}>
        <Input
          label="Название"
          id="name"
          error={errors.name?.message}
          {...register("name")}
          required
        />
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Тип источника</label>
          <select
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-cyan-500/70 transition focus:ring-2 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            {...register("source_type")}
          >
            <option value="postgres">PostgreSQL</option>
            <option value="s3">S3</option>
          </select>
        </div>
        <Input
          label={sourceType === "s3" ? "S3 endpoint host" : "Хост"}
          id="host"
          error={errors.host?.message}
          {...register("host")}
          placeholder={sourceType === "s3" ? "s3.amazonaws.com или minio.local" : ""}
          required
        />
        <Input
          label="Порт"
          id="port"
          type="number"
          error={errors.port?.message}
          {...register("port", { valueAsNumber: true })}
          required
        />
        <Input
          label={sourceType === "s3" ? "S3 bucket" : "База данных"}
          id="database"
          error={errors.database?.message}
          {...register("database")}
          required
        />
        <Input
          label={sourceType === "s3" ? "Access key ID" : "Пользователь"}
          id="username"
          error={errors.username?.message}
          {...register("username")}
          required
        />
        <Input
          label={sourceType === "s3" ? "Secret access key" : "Пароль"}
          id="password"
          type="password"
          error={errors.password?.message}
          {...register("password")}
          placeholder={isEditing ? "Оставьте пустым, чтобы не менять" : ""}
          required={!isEditing}
        />
        <Input
          label="Описание"
          id="description"
          error={errors.description?.message}
          {...register("description")}
        />

        {testResult && (
          <div
            className={`rounded-lg p-3 ${
              testResult.success
                ? "bg-emerald-50 dark:bg-emerald-900/20"
                : "bg-rose-50 dark:bg-rose-900/20"
            }`}
          >
            <ConnectionStatus status={testResult.success ? "valid" : "invalid"} />
            <span className="ml-2 text-sm text-slate-700 dark:text-slate-200">{testResult.message}</span>
          </div>
        )}

        <div className="flex gap-2 pt-4">
          <Button
            type="submit"
            loading={saveMutation.isPending}
            disabled={!name || !host || !database || !username || !sourceType}
          >
            {isEditing ? "Сохранить" : "Создать"}
          </Button>
          {isEditing && (
            <Button
              type="button"
              variant="secondary"
              onClick={() => testMutation.mutate()}
              loading={testMutation.isPending}
              disabled={!sourceId}
            >
              Проверить подключение
            </Button>
          )}
          <Button type="button" variant="secondary" onClick={() => navigate("/sources")}>
            Отмена
          </Button>
        </div>
      </form>
    </div>
  );
}
