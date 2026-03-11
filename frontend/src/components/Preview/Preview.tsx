/**
 * Preview component with table viewer (T067, T068).
 */

import React, { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import api from "../../services/api";
import { ApiErrorNotice } from "../common/ApiErrorNotice";
import { PreviewCellValue } from "./PreviewCellValue";

interface PreviewProps {
  flowId: string;
  sessionId: string;
  tables: string[];
}

export function Preview({ flowId, sessionId, tables }: PreviewProps) {
  const [selectedTable, setSelectedTable] = useState(tables[0] || "");
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState<string | null>(null);
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");

  useEffect(() => {
    if (!selectedTable && tables.length > 0) {
      setSelectedTable(tables[0]);
    }
    if (selectedTable && !tables.includes(selectedTable)) {
      setSelectedTable(tables[0] || "");
    }
  }, [tables, selectedTable]);

  const { data, isLoading, error, isError } = useQuery({
    queryKey: ["preview-data", flowId, sessionId, selectedTable, page, sortBy, sortOrder],
    queryFn: () =>
      api.get(`/flows/${flowId}/preview/${sessionId}/data`, {
        params: {
          table: selectedTable,
          page,
          ...(sortBy ? { sort_by: sortBy, sort_order: sortOrder } : {}),
        },
      }).then((r) => r.data),
    enabled: !!selectedTable,
  });

  const handleSort = (column: string) => {
    if (sortBy === column) {
      setSortOrder((o) => (o === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(column);
      setSortOrder("asc");
    }
  };

  if (isLoading) return <div>Загрузка предпросмотра...</div>;
  if (isError) {
    return (
      <ApiErrorNotice
        error={error}
        fallback="Не удалось загрузить предпросмотр"
        className="rounded-lg p-3 dark:border-rose-900 dark:bg-rose-950/30"
      />
    );
  }

  return (
    <div>
      {/* Table selector */}
      {tables.length > 1 && (
        <div className="mb-4">
          <select
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            value={selectedTable}
            onChange={(e) => {
              setSelectedTable(e.target.value);
              setPage(1);
            }}
          >
            {tables.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Data table */}
      {data && (
        <>
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500 dark:bg-slate-950 dark:text-slate-400">
                <tr>
                  {data.columns?.map((col: string) => (
                    <th
                      key={col}
                      className="cursor-pointer px-4 py-3 hover:bg-slate-100 dark:hover:bg-slate-800"
                      onClick={() => handleSort(col)}
                    >
                      {col}
                      {sortBy === col && (sortOrder === "asc" ? " ^" : " v")}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                {data.rows?.map((row: Record<string, unknown>, i: number) => (
                  <tr key={i}>
                    {data.columns?.map((col: string) => (
                      <td key={col} className="px-4 py-2 text-slate-700 dark:text-slate-300">
                        <PreviewCellValue value={row[col]} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="mt-4 flex items-center justify-between text-sm text-slate-500 dark:text-slate-400">
            <span>
              Страница {data.page} из {data.total_pages} (строк: {data.total})
            </span>
            <div className="flex gap-2">
              <button
                className="rounded-lg border border-slate-300 px-3 py-1 text-slate-700 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Назад
              </button>
              <button
                className="rounded-lg border border-slate-300 px-3 py-1 text-slate-700 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300"
                disabled={page >= (data.total_pages || 1)}
                onClick={() => setPage((p) => p + 1)}
              >
                Далее
              </button>
            </div>
          </div>
        </>
      )}

      {!isLoading && data && (!data.rows || data.rows.length === 0) && (
        <div className="mt-3 text-sm text-slate-500 dark:text-slate-400">
          Нет данных для отображения.
        </div>
      )}
    </div>
  );
}
