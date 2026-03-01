/**
 * Flows list page (T070).
 */

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import api from "../../services/api";
import { Button } from "../../components/common/Button";
import { Table } from "../../components/common/Table";
import { FlowStatusBadge } from "../../components/FlowStatusBadge";

interface Flow {
  id: string;
  name: string;
  status: string;
  source_id: string;
  target_schema: string;
  write_mode: string;
  [key: string]: unknown;
}

const writeModeLabels: Record<string, string> = {
  append: "Добавление",
  upsert: "Обновление и вставка",
  replace: "Перезапись",
};

export default function FlowsList() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const { data: flows = [], isLoading } = useQuery<Flow[]>({
    queryKey: ["flows", page],
    queryFn: () =>
      api
        .get("/flows", { params: { limit: pageSize, offset: (page - 1) * pageSize } })
        .then((r) => r.data),
  });

  const columns = [
    { key: "name", header: "Название" },
    {
      key: "status",
      header: "Статус",
      render: (f: Flow) => <FlowStatusBadge status={f.status} />,
    },
    {
      key: "write_mode",
      header: "Режим",
      render: (f: Flow) => writeModeLabels[f.write_mode] || f.write_mode,
    },
    { key: "target_schema", header: "Цель" },
  ];

  const normalizedSearch = search.trim().toLowerCase();
  const filteredFlows = flows.filter((flow) => {
    if (!normalizedSearch) return true;
    return (
      flow.name.toLowerCase().includes(normalizedSearch) ||
      flow.status.toLowerCase().includes(normalizedSearch) ||
      flow.target_schema.toLowerCase().includes(normalizedSearch)
    );
  });

  if (isLoading) return <div>Загрузка...</div>;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Потоки</h1>
        <Button onClick={() => navigate("/flows/new")}>Создать поток</Button>
      </div>
      <div className="mb-4">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Поиск по имени, статусу или целевой схеме"
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:ring-2 focus:ring-cyan-500/70 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
      </div>

      <Table
        columns={columns}
        data={filteredFlows}
        onRowClick={(f) => navigate(`/flows/${f.id}`)}
        emptyMessage={normalizedSearch ? "Ничего не найдено" : "Потоки еще не созданы"}
      />
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
          Назад
        </Button>
        <Button
          variant="secondary"
          onClick={() => setPage((p) => p + 1)}
          disabled={flows.length < pageSize}
        >
          Далее
        </Button>
      </div>
    </div>
  );
}
