/**
 * Table configuration step - replication method, cursor field (T066).
 */

import React from "react";

interface TableConfig {
  sourceSchema: string;
  sourceTable: string;
  replicationMethod: string;
  replicationKey: string;
}

interface TableConfigStepProps {
  tables: TableConfig[];
  onUpdate: (index: number, config: Partial<TableConfig>) => void;
}

export function TableConfigStep({ tables, onUpdate }: TableConfigStepProps) {
  return (
    <div>
      <h3 className="mb-4 text-lg font-medium">Настройка таблиц</h3>
      <div className="space-y-4">
        {tables.map((table, i) => (
          <div key={i} className="rounded border p-4 dark:border-slate-700">
            <div className="mb-3 font-medium">
              {table.sourceSchema}.{table.sourceTable}
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1 block text-sm text-gray-600 dark:text-slate-400">
                  Метод репликации
                </label>
                <select
                  className="w-full rounded border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                  value={table.replicationMethod}
                  onChange={(e) =>
                    onUpdate(i, { replicationMethod: e.target.value })
                  }
                >
                  <option value="FULL_TABLE">Полная таблица</option>
                  <option value="INCREMENTAL">Инкрементально</option>
                </select>
              </div>
              {table.replicationMethod === "INCREMENTAL" && (
                <div>
                  <label className="mb-1 block text-sm text-gray-600 dark:text-slate-400">
                    Поле курсора
                  </label>
                  <input
                    className="w-full rounded border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                    value={table.replicationKey}
                    onChange={(e) =>
                      onUpdate(i, { replicationKey: e.target.value })
                    }
                    placeholder="например, updated_at"
                  />
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
