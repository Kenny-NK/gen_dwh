/**
 * Audit log page - admin only (T113).
 */

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import api from "../../services/api";
import { Table } from "../../components/common/Table";

interface AuditEvent {
  id: string;
  user_email: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  created_at: string;
  [key: string]: unknown;
}

export default function AuditLog() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 20;
  const { data: events = [], isLoading } = useQuery<AuditEvent[]>({
    queryKey: ["audit", page],
    queryFn: () =>
      api.get("/audit", { params: { limit: pageSize, offset: (page - 1) * pageSize } }).then((r) => r.data),
  });

  const columns = [
    {
      key: "created_at",
      header: "Время",
      render: (e: AuditEvent) => new Date(e.created_at).toLocaleString(),
    },
    { key: "user_email", header: "Пользователь" },
    { key: "action", header: "Действие" },
    { key: "entity_type", header: "Сущность" },
  ];

  const normalizedSearch = search.trim().toLowerCase();
  const filteredEvents = events.filter((event) => {
    if (!normalizedSearch) return true;
    return (
      (event.user_email || "").toLowerCase().includes(normalizedSearch) ||
      event.action.toLowerCase().includes(normalizedSearch) ||
      event.entity_type.toLowerCase().includes(normalizedSearch)
    );
  });

  if (isLoading) return <div>Загрузка...</div>;

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">Журнал аудита</h1>
      <div className="mb-4">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Поиск по пользователю, действию или сущности"
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:ring-2 focus:ring-cyan-500/70 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
      </div>
      <Table
        columns={columns}
        data={filteredEvents}
        emptyMessage={normalizedSearch ? "Ничего не найдено" : "Событий аудита пока нет"}
      />
      <div className="mt-4 flex justify-end gap-2">
        <button
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300"
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          disabled={page === 1}
        >
          Назад
        </button>
        <button
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300"
          onClick={() => setPage((p) => p + 1)}
          disabled={events.length < pageSize}
        >
          Далее
        </button>
      </div>
    </div>
  );
}
