import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { Button } from "../common/Button";
import { Input } from "../common/Input";
import { useToast } from "../common/Toast";
import { useErrorToast } from "../../hooks/useErrorToast";
import {
  type JiraExtractionConfig,
  getJiraProjects,
  getJiraStreams,
  updateJiraExtractionConfig,
} from "../../services/jiraApi";

type Props = {
  sourceId: string;
  initialConfig?: Partial<JiraExtractionConfig> | null;
  config?: JiraExtractionConfig;
  onChange?: (config: JiraExtractionConfig) => void;
  saveMode?: "source" | "none";
};

const defaultConfig: JiraExtractionConfig = {
  streams: ["issues"],
  start_date: null,
  batch_size: 100,
  project_keys: [],
  incremental_enabled: false,
  replication_key: "updated",
  jql: "",
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
  const [config, setConfig] = useState<JiraExtractionConfig>(defaultConfig);
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
    updateConfig((current) => ({
      ...current,
      ...initialConfig,
      streams: initialConfig.streams?.length ? initialConfig.streams : current.streams,
      project_keys: initialConfig.project_keys ?? current.project_keys,
      batch_size: initialConfig.batch_size ?? current.batch_size,
      incremental_enabled: initialConfig.incremental_enabled ?? current.incremental_enabled,
      replication_key: initialConfig.replication_key ?? current.replication_key,
      jql: initialConfig.jql ?? current.jql,
      start_date: initialConfig.start_date ?? current.start_date,
    }));
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
        Выберите проекты и streams, затем сохраните черновик настроек.
      </p>

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

        <div>
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
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
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
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
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

      <Input
        label="JQL (optional)"
        value={resolvedConfig.jql ?? ""}
        onChange={(event) => updateConfig((current) => ({ ...current, jql: event.target.value }))}
      />

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
