import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { Button } from "../common/Button";
import { Input } from "../common/Input";
import { useToast } from "../common/Toast";
import { useErrorToast } from "../../hooks/useErrorToast";
import {
  type JiraExtractionConfig,
  defaultJiraExtractionConfig,
  getJiraProjects,
  getJiraStreams,
  normalizeJiraExtractionConfig,
  updateJiraExtractionConfig,
} from "../../services/jiraApi";

type Props = {
  sourceId: string;
  initialConfig?: Partial<JiraExtractionConfig> | null;
  config?: JiraExtractionConfig;
  onChange?: (config: JiraExtractionConfig) => void;
  saveMode?: "source" | "none";
};

export function JiraStreamSelector({
  sourceId,
  initialConfig,
  config: controlledConfig,
  onChange,
  saveMode = "source",
}: Props) {
  const { addToast } = useToast();
  const { showErrorToast } = useErrorToast();
  const [config, setConfig] = useState<JiraExtractionConfig>(defaultJiraExtractionConfig);
  const resolvedConfig = controlledConfig ?? config;

  const updateConfig = useCallback(
    (next: JiraExtractionConfig | ((current: JiraExtractionConfig) => JiraExtractionConfig)) => {
      if (onChange) {
        const value = typeof next === "function" ? next(resolvedConfig) : next;
        onChange(value);
        return;
      }
      setConfig(next);
    },
    [onChange, resolvedConfig]
  );

  const { data: projects = [], isLoading: projectsLoading } = useQuery({
    queryKey: ["jira-projects", sourceId],
    queryFn: () => getJiraProjects(sourceId),
  });

  const { data: streams = [], isLoading: streamsLoading } = useQuery({
    queryKey: ["jira-streams", sourceId],
    queryFn: () => getJiraStreams(sourceId),
  });

  useEffect(() => {
    if (!initialConfig) return;
    updateConfig(normalizeJiraExtractionConfig(initialConfig));
  }, [initialConfig, updateConfig]);

  const streamDeps = useMemo(() => {
    const deps = new Map<string, string>();
    for (const stream of streams) {
      if (stream.parent_stream) {
        deps.set(stream.name, stream.parent_stream);
      }
    }
    return deps;
  }, [streams]);

  const saveMutation = useMutation({
    mutationFn: () => updateJiraExtractionConfig(sourceId, resolvedConfig),
    onSuccess: () => addToast("success", "Настройки Jira сохранены"),
    onError: (error) => showErrorToast(error, "Не удалось сохранить настройки Jira"),
  });

  const toggleProject = (projectKey: string) => {
    updateConfig((current) => {
      const exists = current.project_keys.includes(projectKey);
      return {
        ...current,
        project_keys: exists
          ? current.project_keys.filter((key) => key !== projectKey)
          : [...current.project_keys, projectKey],
      };
    });
  };

  const toggleStream = (streamName: string) => {
    updateConfig((current) => {
      const next = new Set(current.streams);
      if (next.has(streamName)) {
        next.delete(streamName);
      } else {
        next.add(streamName);
        const parent = streamDeps.get(streamName);
        if (parent) {
          next.add(parent);
        }
      }
      const normalized = Array.from(next);
      if (normalized.length === 0) {
        normalized.push("issues");
      }
      return { ...current, streams: normalized };
    });
  };

  return (
    <div className="mt-8 rounded-lg border border-slate-200 p-4 dark:border-slate-700">
      <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Jira Extraction Config</h2>
      <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
        Выберите streams и режим формирования выборки, затем сохраните черновик настроек.
      </p>

      <div className="mt-4">
        <h3 className="mb-2 text-sm font-semibold text-slate-800 dark:text-slate-200">Streams</h3>
        <div className="max-h-48 space-y-2 overflow-auto rounded-md border border-slate-200 p-3 dark:border-slate-700">
          {streamsLoading && <p className="text-xs text-slate-500">Загрузка streams...</p>}
          {!streamsLoading && streams.length === 0 && (
            <p className="text-xs text-slate-500">Streams не найдены</p>
          )}
          {streams.map((stream) => (
            <label key={stream.name} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={resolvedConfig.streams.includes(stream.name)}
                onChange={() => toggleStream(stream.name)}
              />
              <span>{stream.display_name}</span>
              {stream.parent_stream && (
                <span className="text-xs text-amber-600 dark:text-amber-400">
                  requires: {stream.parent_stream}
                </span>
              )}
            </label>
          ))}
        </div>
      </div>

      <div className="mt-4 inline-flex rounded-lg border border-slate-200 p-1 dark:border-slate-700">
        {[
          { value: "basic", label: "Базовые настройки" },
          { value: "jql", label: "JQL запрос" },
        ].map((tab) => {
          const active = resolvedConfig.query_mode === tab.value;
          return (
            <button
              key={tab.value}
              type="button"
              className={`rounded-md px-3 py-2 text-sm font-medium transition ${
                active
                  ? "bg-cyan-600 text-white"
                  : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
              }`}
              onClick={() =>
                updateConfig((current) => ({
                  ...current,
                  query_mode: tab.value as JiraExtractionConfig["query_mode"],
                }))
              }
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {resolvedConfig.query_mode === "basic" ? (
        <>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <div>
              <h3 className="mb-2 text-sm font-semibold text-slate-800 dark:text-slate-200">Projects</h3>
              <div className="max-h-48 space-y-2 overflow-auto rounded-md border border-slate-200 p-3 dark:border-slate-700">
                {projectsLoading && <p className="text-xs text-slate-500">Загрузка проектов...</p>}
                {!projectsLoading && projects.length === 0 && (
                  <p className="text-xs text-slate-500">Проекты не найдены</p>
                )}
                {projects.map((project) => (
                  <label key={project.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={resolvedConfig.project_keys.includes(project.key)}
                      onChange={() => toggleProject(project.key)}
                    />
                    <span>{project.key}</span>
                    <span className="text-slate-500">- {project.name}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="space-y-4">
              <Input
                label="Batch size"
                type="number"
                value={resolvedConfig.batch_size}
                onChange={(event) =>
                  updateConfig((current) => ({ ...current, batch_size: Number(event.target.value || 100) }))
                }
                min={1}
                max={1000}
              />
              <Input
                label="Replication key"
                value={resolvedConfig.replication_key}
                onChange={(event) =>
                  updateConfig((current) => ({ ...current, replication_key: event.target.value }))
                }
              />
              <label className="inline-flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
                <input
                  type="checkbox"
                  checked={resolvedConfig.incremental_enabled}
                  onChange={(event) =>
                    updateConfig((current) => ({ ...current, incremental_enabled: event.target.checked }))
                  }
                />
                Incremental load
              </label>
              <Input
                label="Start date"
                type="datetime-local"
                value={resolvedConfig.start_date ? String(resolvedConfig.start_date).slice(0, 16) : ""}
                onChange={(event) =>
                  updateConfig((current) => ({
                    ...current,
                    start_date: event.target.value ? new Date(event.target.value).toISOString() : null,
                  }))
                }
              />
            </div>
          </div>
        </>
      ) : (
        <div className="mt-4 space-y-4">
          <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
            В режиме JQL базовые фильтры не применяются. Источник данных определяется только введенным запросом.
          </div>
          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-300">JQL запрос</span>
            <textarea
              value={resolvedConfig.jql ?? ""}
              onChange={(event) => updateConfig((current) => ({ ...current, jql: event.target.value }))}
              rows={6}
              placeholder='Например: project = DWHTOT AND resolved >= "2025-11-01" ORDER BY created DESC'
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:ring-2 focus:ring-cyan-500/70 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            />
          </label>
          <Input
            label="Batch size"
            type="number"
            value={resolvedConfig.batch_size}
            onChange={(event) =>
              updateConfig((current) => ({ ...current, batch_size: Number(event.target.value || 100) }))
            }
            min={1}
            max={1000}
          />
        </div>
      )}


      {saveMode === "source" && (
        <div className="mt-4">
          <Button onClick={() => saveMutation.mutate()} loading={saveMutation.isPending}>
            Сохранить черновик
          </Button>
        </div>
      )}
    </div>
  );
}
