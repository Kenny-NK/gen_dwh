/**
 * Target configuration step (T089).
 */

import React from "react";
import { Input } from "../common/Input";

interface TargetConfig {
  targetSchema: string;
  targetTablePrefix: string;
  writeMode: string;
  upsertKey: string;
}

interface TargetConfigStepProps {
  config: TargetConfig;
  onChange: (config: Partial<TargetConfig>) => void;
}

export function TargetConfigStep({ config, onChange }: TargetConfigStepProps) {
  return (
    <div>
      <h3 className="mb-4 text-lg font-medium">Настройка назначения</h3>
      <div className="space-y-4">
        <Input
          label="Целевая схема"
          value={config.targetSchema}
          onChange={(e) => onChange({ targetSchema: e.target.value })}
          required
        />
        <Input
          label="Префикс таблиц (необязательно)"
          value={config.targetTablePrefix}
          onChange={(e) => onChange({ targetTablePrefix: e.target.value })}
          placeholder="например, raw_"
        />
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-slate-300">
            Режим записи
          </label>
          <select
            className="w-full rounded border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            value={config.writeMode}
            onChange={(e) => onChange({ writeMode: e.target.value })}
          >
            <option value="append">Добавление</option>
            <option value="upsert">Обновление и вставка</option>
            <option value="replace">Перезапись</option>
          </select>
        </div>
        {config.writeMode === "upsert" && (
          <Input
            label="Ключ upsert"
            value={config.upsertKey}
            onChange={(e) => onChange({ upsertKey: e.target.value })}
            placeholder="например, id"
            required
          />
        )}
      </div>
    </div>
  );
}
