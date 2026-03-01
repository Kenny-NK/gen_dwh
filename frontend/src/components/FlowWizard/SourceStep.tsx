/**
 * Source selection step (T064).
 */

import React from "react";
import { useQuery } from "@tanstack/react-query";
import api from "../../services/api";

interface Source {
  id: string;
  name: string;
  host: string;
  database: string;
  connection_status: string;
}

interface SourceStepProps {
  selectedSourceId: string | null;
  onSelect: (sourceId: string) => void;
}

export function SourceStep({ selectedSourceId, onSelect }: SourceStepProps) {
  const { data: sources = [] } = useQuery<Source[]>({
    queryKey: ["sources", { status: "valid" }],
    queryFn: () => api.get("/sources?status=valid").then((r) => r.data),
  });

  return (
    <div>
      <h3 className="mb-4 text-lg font-medium">Выберите источник</h3>
      <div className="space-y-2">
        {sources.map((source) => (
          <div
            key={source.id}
            className={`cursor-pointer rounded border p-4 ${
              selectedSourceId === source.id
                ? "border-blue-500 bg-blue-50 dark:bg-blue-950/20"
                : "border-gray-200 hover:border-gray-300 dark:border-slate-700 dark:hover:border-slate-600"
            }`}
            onClick={() => onSelect(source.id)}
          >
            <div className="font-medium">{source.name}</div>
            <div className="text-sm text-gray-500 dark:text-slate-400">
              {source.host} / {source.database}
            </div>
          </div>
        ))}
        {sources.length === 0 && (
          <p className="text-gray-500 dark:text-slate-400">Нет валидных источников. Сначала создайте источник.</p>
        )}
      </div>
    </div>
  );
}
