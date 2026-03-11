import React, { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { Button } from "../common/Button";
import { Table } from "../common/Table";
import { useToast } from "../common/Toast";
import { useErrorToast } from "../../hooks/useErrorToast";
import { type JiraExtractionConfig, type JiraPreviewResponse, runJiraPreview } from "../../services/jiraApi";

type Props = {
  sourceId: string;
  config?: Partial<JiraExtractionConfig>;
  onPreviewReady?: (data: JiraPreviewResponse) => void;
  createFlowLink?: string | null;
};

type PreviewRow = Record<string, unknown> & { id: string };

function normalizeRows(rows: Array<Record<string, unknown>>): PreviewRow[] {
  return rows.map((row, index) => ({ ...row, id: String(row.id ?? index + 1) }));
}

function stringifyCellValue(value: unknown): string {
  if (typeof value !== "object" || value === null) {
    return String(value ?? "");
  }
  try {
    return JSON.stringify(value);
  } catch {
    return "[Object]";
  }
}

export function JiraPreviewResults({ sourceId, config, onPreviewReady, createFlowLink }: Props) {
  const navigate = useNavigate();
  const { addToast } = useToast();
  const { getErrorMessage, showErrorToast } = useErrorToast();
  const [selectedStream, setSelectedStream] = useState<string>("");
  const [errorDetails, setErrorDetails] = useState<{
    message: string;
    error_type?: string;
    suggestion?: string;
  } | null>(null);

  const previewMutation = useMutation({
    mutationFn: () =>
      runJiraPreview(sourceId, {
        streams: config?.streams,
        project_keys: config?.project_keys,
        jql: config?.jql,
        batch_size: config?.batch_size,
      }),
    onSuccess: (data) => {
      setErrorDetails(null);
      const stream = data.streams[0] ?? "";
      setSelectedStream(stream);
      onPreviewReady?.(data);
      addToast("success", "Preview готов");
    },
    onError: (error: unknown) => {
      const fallback = getErrorMessage(error, "Не удалось запустить preview");
      const maybePayload = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
      if (maybePayload && typeof maybePayload === "object") {
        const detail = maybePayload as { message?: string; error_type?: string; suggestion?: string };
        setErrorDetails({
          message: detail.message || fallback,
          error_type: detail.error_type,
          suggestion: detail.suggestion,
        });
      } else {
        setErrorDetails({ message: fallback });
      }
      showErrorToast(error, "Не удалось запустить preview");
    },
  });

  const streams = previewMutation.data?.streams ?? [];
  const rows = useMemo(() => {
    if (!selectedStream) return [];
    return normalizeRows(previewMutation.data?.records?.[selectedStream] ?? []);
  }, [previewMutation.data, selectedStream]);

  const columns = useMemo(() => {
      if (rows.length === 0) return [];
    return Object.keys(rows[0]).map((key) => ({
      key,
      header: key,
      render: (row: PreviewRow) => stringifyCellValue(row[key]),
    }));
  }, [rows]);

  const schema = useMemo(() => {
    if (!selectedStream) return null;
    return previewMutation.data?.schema?.[selectedStream] ?? null;
  }, [previewMutation.data, selectedStream]);

  return (
    <div className="mt-8 rounded-lg border border-slate-200 p-4 dark:border-slate-700">
      <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Preview данных Jira</h2>
      <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
        Запустите preview, чтобы проверить схему и sample records перед созданием потока.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button type="button" onClick={() => previewMutation.mutate()} loading={previewMutation.isPending}>
          Запустить preview
        </Button>
        {previewMutation.data?.success && createFlowLink && (
          <Button
            type="button"
            variant="secondary"
            onClick={() => navigate(createFlowLink)}
          >
            Создать поток
          </Button>
        )}
      </div>

      {errorDetails && (
        <div className="mt-4 rounded-md bg-rose-50 p-3 text-sm text-rose-700 dark:bg-rose-900/20 dark:text-rose-300">
          <p>{errorDetails.message}</p>
          {errorDetails.error_type && <p className="mt-1">Тип: {errorDetails.error_type}</p>}
          {errorDetails.suggestion && <p className="mt-1">Рекомендация: {errorDetails.suggestion}</p>}
        </div>
      )}

      {previewMutation.data?.success && (
        <div className="mt-4 space-y-4">
          <div className="flex items-center gap-3">
            <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Stream</label>
            <select
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
              value={selectedStream}
              onChange={(event) => setSelectedStream(event.target.value)}
            >
              {streams.map((stream) => (
                <option key={stream} value={stream}>
                  {stream}
                </option>
              ))}
            </select>
          </div>

          {columns.length > 0 ? (
            <Table columns={columns} data={rows} emptyMessage="Нет записей для preview" />
          ) : (
            <p className="text-sm text-slate-500">Нет sample records для выбранного stream.</p>
          )}

          <div>
            <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">Schema</h3>
            <pre className="mt-2 overflow-auto rounded-md bg-slate-100 p-3 text-xs dark:bg-slate-900">
              {JSON.stringify(schema ?? {}, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
