/**
 * Common Table component (T029).
 */

import React from "react";

interface Column<T> {
  key: string;
  header: string;
  render?: (item: T) => React.ReactNode;
}

interface TableProps<T> {
  columns: Column<T>[];
  data: T[];
  onRowClick?: (item: T) => void;
  emptyMessage?: string;
}

export function Table<T extends Record<string, unknown>>({
  columns,
  data,
  onRowClick,
  emptyMessage = "Нет данных",
}: TableProps<T>) {
  if (data.length === 0) {
    return (
      <div className="app-card py-10 text-center text-sm text-slate-500 dark:text-slate-400">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="app-card overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400">
          <tr>
            {columns.map((col) => (
              <th key={col.key} scope="col" className="px-4 py-3">
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
          {data.map((item, i) => (
            <tr
              key={String(item.id ?? i)}
              className={onRowClick ? "cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/70" : ""}
              onClick={() => onRowClick?.(item)}
              tabIndex={onRowClick ? 0 : undefined}
              onKeyDown={(event) => {
                if (!onRowClick) return;
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onRowClick(item);
                }
              }}
            >
              {columns.map((col, index) => (
                <td
                  key={col.key}
                  className={`px-4 py-3 text-slate-700 dark:text-slate-200 ${
                    index === 0 ? "font-medium text-slate-900 dark:text-slate-100" : ""
                  }`}
                >
                  {col.render ? col.render(item) : String(item[col.key] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
