/**
 * Cron expression builder/validator (T091).
 */

import React, { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import api from "../services/api";
import { Input } from "./common/Input";
import { formatDateTime } from "../utils/formatDate";

interface ScheduleBuilderProps {
  value: string;
  onChange: (value: string) => void;
}

const presets = [
  { label: "Каждый час", value: "0 * * * *" },
  { label: "Каждые 6 часов", value: "0 */6 * * *" },
  { label: "Каждые 12 часов", value: "0 */12 * * *" },
  { label: "Ежедневно в 00:00", value: "0 0 * * *" },
  { label: "Еженедельно (воскресенье)", value: "0 0 * * 0" },
];

export function ScheduleBuilder({ value, onChange }: ScheduleBuilderProps) {
  const [nextTimes, setNextTimes] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const validateMutation = useMutation({
    mutationFn: (expr: string) =>
      api
        .post("/schedules/validate", {
          cron_expression: expr,
        })
        .then((r) => r.data),
    onSuccess: (data) => {
      if (data.valid) {
        setNextTimes(data.next_times || []);
        setError(null);
      } else {
        setNextTimes([]);
        setError(data.error);
      }
    },
  });

  useEffect(() => {
    if (value) {
      const timer = setTimeout(() => validateMutation.mutate(value), 500);
      return () => clearTimeout(timer);
    }
    setNextTimes([]);
    setError(null);
  }, [value, validateMutation]);

  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-2">
        {presets.map((p) => (
          <button
            key={p.value}
            type="button"
            className={`rounded border px-2 py-1 text-xs ${
              value === p.value ? "border-blue-500 bg-blue-50 dark:bg-blue-950/20" : "hover:bg-gray-50 dark:hover:bg-slate-800"
            }`}
            onClick={() => onChange(p.value)}
          >
            {p.label}
          </button>
        ))}
      </div>

      <Input
        label="Cron-выражение"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="* * * * *"
        error={error || undefined}
      />

      {nextTimes.length > 0 && (
        <div className="mt-2 text-xs text-gray-500 dark:text-slate-400">
          <div className="font-medium">Ближайшие запуски:</div>
          {nextTimes.map((t, i) => (
            <div key={i}>{formatDateTime(t)}</div>
          ))}
        </div>
      )}
    </div>
  );
}
