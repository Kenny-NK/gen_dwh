import React from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";

import api from "../../services/api";
import { Button } from "../../components/common/Button";
import { Input } from "../../components/common/Input";
import { useToast } from "../../components/common/Toast";
import { JiraPreviewResults } from "../../components/JiraConfig/JiraPreviewResults";
import { JiraStreamSelector } from "../../components/JiraConfig/JiraStreamSelector";
import { useErrorToast } from "../../hooks/useErrorToast";
import type {
  JiraExtractionConfig,
  JiraFlowStreamConfig,
  JiraPreviewResponse,
} from "../../services/jiraApi";

type Source = {
  id: string;
  name: string;
  source_type: "postgres" | "s3" | "jira";
  connection_status: string;
  jira_auth_type?: "basic_token" | "basic_password" | "pat_bearer" | null;
  jira_runtime_engine?: "meltano" | "native" | null;
  extraction_config?: JiraExtractionConfig | null;
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

const defaultJiraConfig: JiraExtractionConfig = {
  streams: ["issues"],
  start_date: null,
  batch_size: 100,
  project_keys: [],
  incremental_enabled: false,
  replication_key: "updated",
  jql: "",
};

function defaultStreamConfig(stream: string): JiraFlowStreamConfig {
  const incrementalStreams = new Set(["issues", "worklogs", "changelogs", "issue_comments"]);
  return {
    stream,
    replication_method: incrementalStreams.has(stream) ? "INCREMENTAL" : "FULL_TABLE",
    replication_key: stream === "changelogs" || stream === "issue_comments" ? "created" : "updated",
  };
}

export default function FlowCreate() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const { showErrorToast } = useErrorToast();
  const querySourceId = React.useMemo(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("sourceId") ?? "";
  }, []);
  const [jiraStreams, setJiraStreams] = React.useState<JiraFlowStreamConfig[]>([]);
  const [jiraConfig, setJiraConfig] = React.useState<JiraExtractionConfig>(defaultJiraConfig);
  const [jiraPreview, setJiraPreview] = React.useState<JiraPreviewResponse | null>(null);
  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isValid },
  } = useForm<FlowPayload>({
    resolver: zodResolver(flowSchema),
    defaultValues: {
      ...defaultPayload,
      source_id: querySourceId || defaultPayload.source_id,
    },
    mode: "onChange",
  });

  const { data: sources = [] } = useQuery<Source[]>({
    queryKey: ["sources", "valid-for-flow"],
    queryFn: () => api.get("/sources?status=valid").then((r) => r.data.items ?? []),
  });

  React.useEffect(() => {
    if (!querySourceId) return;
    setValue("source_id", querySourceId, { shouldValidate: true });
  }, [querySourceId, setValue]);

  const selectedSourceId = watch("source_id");
  const selectedSource = sources.find((source) => source.id === selectedSourceId);
  const isJiraSource = selectedSource?.source_type === "jira";

  React.useEffect(() => {
    if (!selectedSourceId || !isJiraSource) {
      setJiraStreams([]);
      setJiraConfig(defaultJiraConfig);
      setJiraPreview(null);
      return;
    }
    const nextConfig: JiraExtractionConfig = {
      ...defaultJiraConfig,
      ...(selectedSource?.extraction_config ?? {}),
      streams:
        selectedSource?.extraction_config?.streams?.length
          ? selectedSource.extraction_config.streams
          : defaultJiraConfig.streams,
      project_keys: selectedSource?.extraction_config?.project_keys ?? defaultJiraConfig.project_keys,
    };
    setJiraConfig(nextConfig);
    setJiraPreview(null);
  }, [isJiraSource, selectedSource, selectedSourceId]);

  React.useEffect(() => {
    if (!isJiraSource) {
      return;
    }
    const nextStreams = jiraConfig.streams.length > 0 ? jiraConfig.streams : ["issues"];
    setJiraStreams((current) =>
      nextStreams.map((stream) => current.find((item) => item.stream === stream) ?? defaultStreamConfig(stream))
    );
  }, [isJiraSource, jiraConfig.streams]);

  const createFlow = useMutation({
    mutationFn: async (payload: FlowPayload) => {
      const body: Record<string, unknown> = {
        ...payload,
        extraction_config: isJiraSource ? jiraConfig : undefined,
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
      const flow = response.data as { id: string };

      if (isJiraSource) {
        const tablePayloads = jiraStreams.length > 0
          ? jiraStreams
          : [{ stream: "issues", replication_method: "INCREMENTAL" as const, replication_key: "updated" }];
        for (const stream of tablePayloads) {
          await api.post(`/flows/${flow.id}/tables`, {
            source_schema: "jira",
            source_table: stream.stream,
            replication_method: stream.replication_method,
            replication_key: stream.replication_method === "INCREMENTAL" ? stream.replication_key : null,
          });
        }
      }

      return flow;
    },
    onSuccess: (flow) => {
      addToast("success", "Поток создан");
      queryClient.invalidateQueries({ queryKey: ["flows"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-flows"] });
      navigate(`/flows/${flow.id}`);
    },
    onError: (error: unknown) => {
      showErrorToast(error, "Не удалось создать поток");
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
                {source.name} (
                {source.source_type === "s3"
                  ? "S3"
                  : source.source_type === "jira"
                    ? `Jira • ${source.jira_runtime_engine === "native" ? "Native PAT" : "Meltano Basic"}`
                    : "PostgreSQL"}
                )
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

        {isJiraSource && (
          <>
            <div className="rounded-lg border border-cyan-200 bg-cyan-50 px-3 py-2 text-sm text-cyan-900 dark:border-cyan-900 dark:bg-cyan-950/40 dark:text-cyan-100">
              Источник будет выполняться через{" "}
              <strong>{selectedSource?.jira_runtime_engine === "native" ? "native Jira extractor" : "Meltano"}</strong>.
            </div>
            <JiraStreamSelector
              sourceId={selectedSourceId}
              initialConfig={selectedSource?.extraction_config ?? undefined}
              config={jiraConfig}
              onChange={setJiraConfig}
              saveMode="none"
            />

            <JiraPreviewResults
              sourceId={selectedSourceId}
              config={jiraConfig}
              onPreviewReady={setJiraPreview}
            />

            <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-700">
              <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                Jira stream configuration
              </h2>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                Streams берутся из Jira Extraction Config. При необходимости настрой режим загрузки перед созданием потока.
              </p>
              {jiraPreview && (
                <p className="mt-2 text-xs text-emerald-700 dark:text-emerald-400">
                  Preview выполнен: {jiraPreview.record_count} sample records.
                </p>
              )}
              <div className="mt-3 space-y-3">
                {jiraStreams.map((stream, index) => (
                  <div
                    key={`${stream.stream}-${index}`}
                    className="grid gap-2 rounded-md border border-slate-200 p-3 dark:border-slate-700 md:grid-cols-3"
                  >
                    <div className="text-sm font-medium text-slate-700 dark:text-slate-300">{stream.stream}</div>
                    <select
                      value={stream.replication_method}
                      onChange={(event) =>
                        setJiraStreams((current) =>
                          current.map((item, idx) =>
                            idx === index
                              ? {
                                  ...item,
                                  replication_method: event.target.value as "FULL_TABLE" | "INCREMENTAL",
                                }
                              : item
                          )
                        )
                      }
                      className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
                    >
                      <option value="FULL_TABLE">FULL_TABLE</option>
                      <option value="INCREMENTAL">INCREMENTAL</option>
                    </select>
                    <Input
                      value={stream.replication_key}
                      onChange={(event) =>
                        setJiraStreams((current) =>
                          current.map((item, idx) =>
                            idx === index ? { ...item, replication_key: event.target.value } : item
                          )
                        )
                      }
                      disabled={stream.replication_method !== "INCREMENTAL"}
                      placeholder="replication key"
                    />
                  </div>
                ))}
              </div>
            </div>
          </>
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
