/**
 * Source form component - create/edit (T046, T048, T049).
 */

import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import api from "../../services/api";
import { Button } from "../../components/common/Button";
import { Input } from "../../components/common/Input";
import { ConnectionStatus } from "../../components/ConnectionStatus";
import { useToast } from "../../components/common/Toast";
import { useErrorToast } from "../../hooks/useErrorToast";
import type { JiraExtractionConfig } from "../../services/jiraApi";

type SourceType = "postgres" | "s3" | "jira";
type JiraAuthType = "basic_token" | "basic_password" | "pat_bearer";

const sourceTypeValues = ["postgres", "s3", "jira"] as const;

const sourceBaseSchema = z
  .object({
    name: z.string().trim().min(1, "Название обязательно").max(255, "Максимум 255 символов"),
    source_type: z.union([z.enum(sourceTypeValues), z.literal("")]),
    host: z.string().trim().min(1, "Хост обязателен").max(255, "Максимум 255 символов"),
    port: z.coerce.number().int().min(1, "Минимум 1").max(65535, "Максимум 65535"),
    database: z.string().max(255, "Максимум 255 символов"),
    jira_auth_type: z.enum(["basic_token", "basic_password", "pat_bearer"]).default("basic_token"),
    username: z.string().trim().max(255, "Максимум 255 символов"),
    password: z.string(),
    description: z.string().optional().default(""),
  })
  .superRefine((value, ctx) => {
    if (!value.source_type) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["source_type"],
        message: "Выберите тип источника",
      });
      return;
    }

    if ((value.source_type === "postgres" || value.source_type === "s3") && !value.database.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["database"],
        message: value.source_type === "s3" ? "Bucket обязателен" : "База данных обязательна",
      });
    }
    if ((value.source_type === "postgres" || value.source_type === "s3") && !value.username.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["username"],
        message: "Пользователь обязателен",
      });
    }
    if (value.source_type === "jira") {
      if (!/^https:\/\/.+/i.test(value.host.trim())) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["host"],
          message: "Base URL должен начинаться с https://",
        });
      }
      if ((value.jira_auth_type === "basic_token" || value.jira_auth_type === "basic_password") && !value.username.trim()) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["username"],
          message: "Введите логин или email Jira",
        });
      }
      if (value.port !== 443) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["port"],
          message: "Для Jira используется порт 443",
        });
      }
    }
  });

const sourceCreateSchema = sourceBaseSchema.superRefine((value, ctx) => {
  if (value.password.trim().length > 0) return;
  ctx.addIssue({
    code: z.ZodIssueCode.custom,
    path: ["password"],
    message: value.source_type === "jira" ? "API token обязателен" : "Пароль обязателен",
  });
});

const sourceEditSchema = sourceBaseSchema;
type SourceFormData = z.infer<typeof sourceBaseSchema>;

interface SourceResponse {
  name: string;
  source_type: SourceType;
  jira_auth_type?: JiraAuthType | null;
  jira_runtime_engine?: "meltano" | "native" | null;
  host: string;
  port: number;
  database: string;
  username: string;
  description?: string | null;
  token_mask?: string | null;
  extraction_config?: JiraExtractionConfig | null;
}

interface SourceTestResponse {
  success: boolean;
  message: string;
}

interface SourceTypeOption {
  value: SourceType;
  title: string;
  description: string;
  icon: React.ReactNode;
}

const SOURCE_TYPE_OPTIONS: SourceTypeOption[] = [
  {
    value: "postgres",
    title: "PostgreSQL",
    description: "Подключение к реляционной базе PostgreSQL",
    icon: (
      <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.8">
        <ellipse cx="12" cy="6" rx="7" ry="3.2" />
        <path d="M5 6v6c0 1.8 3.1 3.2 7 3.2s7-1.4 7-3.2V6" />
        <path d="M5 12v6c0 1.8 3.1 3.2 7 3.2s7-1.4 7-3.2v-6" />
      </svg>
    ),
  },
  {
    value: "s3",
    title: "S3",
    description: "Файлы из S3 или S3-совместимого хранилища",
    icon: (
      <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M6.5 9.5A4.5 4.5 0 0 1 11 5a5 5 0 0 1 4.6 3 3.5 3.5 0 1 1 .9 6.9H7a3 3 0 1 1-.5-5.4" />
        <path d="M12 11v8" />
        <path d="m9.5 16 2.5 3 2.5-3" />
      </svg>
    ),
  },
  {
    value: "jira",
    title: "Jira",
    description: "Задачи и проекты из Jira",
    icon: (
      <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M8 5h8l3 3-7 7-3-3z" />
        <path d="M5 8h8l3 3-7 7-3-3z" />
      </svg>
    ),
  },
];

const SOURCE_FORM_DRAFT_KEY = "source-form-draft-v1";

const defaultForm: SourceFormData = {
  name: "",
  source_type: "",
  host: "",
  port: 5432,
  database: "",
  jira_auth_type: "basic_token",
  username: "",
  password: "",
  description: "",
};

function isSourceType(value: string): value is SourceType {
  return value === "postgres" || value === "s3" || value === "jira";
}

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
  const { showErrorToast } = useErrorToast();
  const {
    register,
    handleSubmit,
    reset,
    setValue,
    getValues,
    trigger,
    watch,
    formState: { errors },
  } = useForm<SourceFormData>({
    resolver: zodResolver(schema),
    defaultValues: defaultForm,
  });

  const sourceType = watch("source_type");
  const hasSelectedSourceType = isSourceType(sourceType);

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
      showErrorToast(sourceError, "Ошибка запроса. Проверьте параметры и попробуйте снова.");
    }
  }, [isSourceError, sourceError, showErrorToast]);

  useEffect(() => {
    if (source) {
      reset({
        name: source.name,
        source_type: source.source_type,
        host: source.host,
        port: source.port,
        database: source.database,
        jira_auth_type: source.jira_auth_type ?? source.extraction_config?.auth_type ?? "basic_token",
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
    if (isEditing || !hasSelectedSourceType) return;
    const currentHost = getValues("host");
    const currentPort = getValues("port");

    if (sourceType === "s3") {
      if (!currentHost) {
        setValue("host", "s3.amazonaws.com", { shouldValidate: true });
      }
      if (!currentPort || currentPort === 5432) {
        setValue("port", 443, { shouldValidate: true });
      }
      return;
    }

    if (sourceType === "jira") {
      if (!currentPort || currentPort !== 443) {
        setValue("port", 443, { shouldValidate: true });
      }
      setValue("database", "", { shouldValidate: true });
      if (!getValues("jira_auth_type")) {
        setValue("jira_auth_type", "basic_token", { shouldValidate: true });
      }
    }
  }, [getValues, hasSelectedSourceType, isEditing, setValue, sourceType]);

  const saveMutation = useMutation({
    mutationFn: (data: SourceFormData) => {
      if (!isSourceType(data.source_type)) {
        throw new Error("Выберите тип источника");
      }
      const payload = {
        ...data,
        source_type: data.source_type,
        jira_auth_type: data.source_type === "jira" ? data.jira_auth_type : undefined,
        database: data.source_type === "jira" ? "" : data.database,
        port: data.source_type === "jira" ? 443 : data.port,
      };
      return isEditing
        ? api.patch(`/sources/${id}`, {
            ...payload,
            password: payload.password.trim() || undefined,
          })
        : api.post("/sources", payload);
    },
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
      showErrorToast(error, "Ошибка запроса. Проверьте параметры и попробуйте снова.");
    },
  });

  const testMutation = useMutation({
    mutationFn: () => {
      if (isEditing) {
        return api.post(`/sources/${id}/test`).then((r) => r.data);
      }

      const values = getValues();
      if (!isSourceType(values.source_type)) {
        throw new Error("Выберите тип источника");
      }
      return api
        .post("/sources/test-connection", {
          source_type: values.source_type,
          jira_auth_type: values.source_type === "jira" ? values.jira_auth_type : undefined,
          host: values.host,
          port: values.source_type === "jira" ? 443 : values.port,
          database: values.source_type === "jira" ? "" : values.database,
          username: values.username,
          password: values.password,
        })
        .then((r) => r.data);
    },
    onSuccess: (data: SourceTestResponse) => {
      setTestResult(data);
      addToast("info", data.success ? "Подключение успешно" : data.message);
    },
    onError: (error) => {
      showErrorToast(error, "Ошибка запроса. Проверьте параметры и попробуйте снова.");
    },
  });

  const name = watch("name");
  const host = watch("host");
  const database = watch("database");
  const jiraAuthType = watch("jira_auth_type");
  const username = watch("username");
  const jiraRuntimeEngine = sourceType === "jira" && jiraAuthType === "pat_bearer" ? "native" : "meltano";
  const selectSourceType = (next: SourceType) => {
    setValue("source_type", next, { shouldValidate: true, shouldDirty: true });
    setTestResult(null);
  };

  const canSubmit =
    !!name &&
    !!host &&
    hasSelectedSourceType &&
    (sourceType === "jira" ? jiraAuthType === "pat_bearer" || !!username : !!username && !!database);

  return (
    <div className="mx-auto max-w-3xl app-card p-6">
      <h1 className="mb-6 text-2xl font-bold text-slate-900 dark:text-slate-100">
        {isEditing ? "Редактирование источника" : "Новый источник"}
      </h1>

      <form className="space-y-5" onSubmit={handleSubmit((values) => saveMutation.mutate(values))}>
        <Input label="Название" id="name" error={errors.name?.message} {...register("name")} required />

        <div className="space-y-2">
          <div>
            <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Шаг 1. Выберите тип источника</h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Выберите карточку источника, затем заполните реквизиты подключения.
            </p>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            {SOURCE_TYPE_OPTIONS.map((option) => {
              const selected = sourceType === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => selectSourceType(option.value)}
                  className={`rounded-xl border p-4 text-left transition ${
                    selected
                      ? "border-cyan-500 bg-cyan-50 dark:border-cyan-400 dark:bg-cyan-900/20"
                      : "border-slate-300 bg-white hover:border-cyan-300 dark:border-slate-700 dark:bg-slate-900"
                  }`}
                >
                  <div className="mb-2 inline-flex rounded-lg bg-slate-100 p-2 text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                    {option.icon}
                  </div>
                  <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{option.title}</h3>
                  <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">{option.description}</p>
                </button>
              );
            })}
          </div>
          {errors.source_type?.message && (
            <p className="text-xs text-rose-500">{errors.source_type.message}</p>
          )}
        </div>

        {hasSelectedSourceType && (
          <>
            <div>
              <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Шаг 2. Введите реквизиты подключения</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                После ввода можно проверить подключение перед сохранением.
              </p>
            </div>

            <Input
              label={sourceType === "s3" ? "S3 endpoint host" : sourceType === "jira" ? "Jira Base URL" : "Хост"}
              id="host"
              error={errors.host?.message}
              {...register("host")}
              placeholder={
                sourceType === "s3"
                  ? "s3.amazonaws.com или minio.local"
                  : sourceType === "jira"
                    ? "https://company.atlassian.net"
                    : ""
              }
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

            {sourceType !== "jira" && (
              <Input
                label={sourceType === "s3" ? "S3 bucket" : "База данных"}
                id="database"
                error={errors.database?.message}
                {...register("database")}
                required
              />
            )}

            {sourceType === "jira" && (
              <div className="space-y-2">
                <label
                  htmlFor="jira_auth_type"
                  className="block text-sm font-medium text-slate-700 dark:text-slate-200"
                >
                  Jira Authentication Type
                </label>
                <select
                  id="jira_auth_type"
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-cyan-500/70 transition focus:ring-2 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                  {...register("jira_auth_type")}
                >
                  <option value="basic_token">Username or Email + API Token (Basic)</option>
                  <option value="basic_password">Username + Password (Basic)</option>
                  <option value="pat_bearer">Personal Access Token (Bearer)</option>
                </select>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Для Jira Cloud чаще используется Basic c API token. Для вашего on-prem Jira можно использовать Basic с логином и паролем.
                </p>
                <p className="text-xs font-medium text-cyan-700 dark:text-cyan-300">
                  Режим выполнения: {jiraRuntimeEngine === "native" ? "Native extractor" : "Meltano"}
                </p>
                {isEditing && source?.jira_runtime_engine && (
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Сохраненный режим источника: {source.jira_runtime_engine === "native" ? "Native extractor" : "Meltano"}
                  </p>
                )}
              </div>
            )}

            <Input
              label={
                sourceType === "s3"
                  ? "Access key ID"
                  : sourceType === "jira"
                    ? jiraAuthType === "pat_bearer"
                      ? "Jira Username or Email (optional)"
                      : "Jira Username or Email"
                    : "Пользователь"
              }
              id="username"
              error={errors.username?.message}
              {...register("username")}
              required={sourceType !== "jira" || jiraAuthType !== "pat_bearer"}
              placeholder={sourceType === "jira" && jiraAuthType === "pat_bearer" ? "Необязательно для Bearer PAT" : ""}
            />

            <Input
              label={
                sourceType === "s3"
                  ? "Secret access key"
                  : sourceType === "jira"
                    ? jiraAuthType === "pat_bearer"
                      ? "Jira Personal Access Token"
                      : jiraAuthType === "basic_password"
                        ? "Jira Password"
                        : "Jira API Token"
                    : "Пароль"
              }
              id="password"
              type="password"
              error={errors.password?.message}
              {...register("password")}
              placeholder={isEditing ? "Оставьте пустым, чтобы не менять" : ""}
              required={!isEditing}
            />

            {isEditing && sourceType === "jira" && source?.token_mask && (
              <p className="text-xs text-slate-500 dark:text-slate-400">Текущий token: {source.token_mask}</p>
            )}

            <Input
              label="Описание"
              id="description"
              error={errors.description?.message}
              {...register("description")}
            />

            {testResult && (
              <div
                className={`rounded-lg p-3 ${
                  testResult.success ? "bg-emerald-50 dark:bg-emerald-900/20" : "bg-rose-50 dark:bg-rose-900/20"
                }`}
              >
                <ConnectionStatus status={testResult.success ? "valid" : "invalid"} />
                <span className="ml-2 text-sm text-slate-700 dark:text-slate-200">{testResult.message}</span>
              </div>
            )}
          </>
        )}

        <div className="flex flex-wrap gap-2 pt-2">
          <Button type="submit" loading={saveMutation.isPending} disabled={!canSubmit}>
            {isEditing ? "Сохранить" : "Создать"}
          </Button>

          {hasSelectedSourceType && (
            <Button
              type="button"
              variant="secondary"
              onClick={async () => {
                const fields: Array<keyof SourceFormData> = [
                  "source_type",
                  "host",
                  "port",
                  "username",
                  "password",
                ];
                if (sourceType !== "jira") {
                  fields.push("database");
                }
                const ok = await trigger(fields);
                if (!ok) return;
                testMutation.mutate();
              }}
              loading={testMutation.isPending}
            >
              Проверить подключение
            </Button>
          )}

          <Button type="button" variant="secondary" onClick={() => navigate("/sources")}>Отмена</Button>
        </div>
      </form>
    </div>
  );
}
