/**
 * Schedule configuration step (T090).
 */

import React from "react";
import { Input } from "../common/Input";
import { ScheduleBuilder } from "../ScheduleBuilder";

interface ScheduleConfig {
  scheduleType: string;
  cronExpression: string;
  intervalMinutes: number;
  timezone: string;
}

interface ScheduleStepProps {
  config: ScheduleConfig;
  onChange: (config: Partial<ScheduleConfig>) => void;
}

export function ScheduleStep({ config, onChange }: ScheduleStepProps) {
  return (
    <div>
      <h3 className="mb-4 text-lg font-medium">Расписание</h3>
      <div className="space-y-4">
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-slate-300">
            Тип расписания
          </label>
          <select
            className="w-full rounded border px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            value={config.scheduleType}
            onChange={(e) => onChange({ scheduleType: e.target.value })}
          >
            <option value="manual">Вручную</option>
            <option value="cron">Cron</option>
            <option value="interval">Интервал</option>
          </select>
        </div>

        {config.scheduleType === "cron" && (
          <ScheduleBuilder
            value={config.cronExpression}
            onChange={(v) => onChange({ cronExpression: v })}
          />
        )}

        {config.scheduleType === "interval" && (
          <Input
            label="Интервал (минуты)"
            type="number"
            value={config.intervalMinutes}
            onChange={(e) => {
              const parsed = Number.parseInt(e.target.value, 10);
              onChange({ intervalMinutes: Number.isNaN(parsed) ? 5 : parsed });
            }}
            min={5}
            max={10080}
          />
        )}

        <Input
          label="Часовой пояс"
          value={config.timezone}
          onChange={(e) => onChange({ timezone: e.target.value })}
        />
      </div>
    </div>
  );
}
