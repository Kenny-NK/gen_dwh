/**
 * Table selection step (T065).
 */

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import api from "../../services/api";

interface TableInfo {
  name: string;
  row_count: number;
  columns: { name: string; data_type: string }[];
}

interface TableSelectionStepProps {
  sourceId: string;
  selectedTables: string[];
  onSelect: (tables: string[]) => void;
}

export function TableSelectionStep({
  sourceId,
  selectedTables,
  onSelect,
}: TableSelectionStepProps) {
  const [selectedSchema, setSelectedSchema] = useState("public");

  const { data: schemas = [] } = useQuery<string[]>({
    queryKey: ["source-schemas", sourceId],
    queryFn: () => api.get(`/sources/${sourceId}/schemas`).then((r) => r.data),
    enabled: !!sourceId,
  });

  const { data: tables = [] } = useQuery<TableInfo[]>({
    queryKey: ["source-tables", sourceId, selectedSchema],
    queryFn: () =>
      api.get(`/sources/${sourceId}/schemas/${selectedSchema}/tables`).then((r) => r.data),
    enabled: !!sourceId && !!selectedSchema,
  });

  const toggleTable = (tableName: string) => {
    const key = `${selectedSchema}.${tableName}`;
    if (selectedTables.includes(key)) {
      onSelect(selectedTables.filter((t) => t !== key));
    } else {
      onSelect([...selectedTables, key]);
    }
  };

  return (
    <div>
      <h3 className="mb-4 text-lg font-medium">Выбор таблиц</h3>

      <div className="mb-4">
        <select
          className="rounded border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          value={selectedSchema}
          onChange={(e) => setSelectedSchema(e.target.value)}
        >
          {schemas.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-2">
        {tables.map((table) => {
          const key = `${selectedSchema}.${table.name}`;
          return (
            <label
              key={table.name}
              className="flex items-center gap-3 rounded border p-3 hover:bg-gray-50 dark:border-slate-700 dark:hover:bg-slate-800"
            >
              <input
                type="checkbox"
                checked={selectedTables.includes(key)}
                onChange={() => toggleTable(table.name)}
              />
              <div>
                <div className="font-medium">{table.name}</div>
                <div className="text-xs text-gray-500 dark:text-slate-400">
                  {table.row_count} строк, {table.columns.length} колонок
                </div>
              </div>
            </label>
          );
        })}
      </div>
    </div>
  );
}
