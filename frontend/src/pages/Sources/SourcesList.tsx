/**
 * Sources list page (T045, T050).
 */

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "../../services/api";
import { Button } from "../../components/common/Button";
import { Table } from "../../components/common/Table";
import { Modal } from "../../components/common/Modal";
import { ConnectionStatus } from "../../components/ConnectionStatus";
import { useToast } from "../../components/common/Toast";

interface Source {
  id: string;
  name: string;
  description?: string | null;
  host: string;
  port: number;
  database: string;
  connection_status: string;
  last_validated_at: string | null;
  [key: string]: unknown;
}

export default function SourcesList() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const { data: sources = [], isLoading } = useQuery<Source[]>({
    queryKey: ["sources", page],
    queryFn: () =>
      api
        .get("/sources", { params: { limit: pageSize, offset: (page - 1) * pageSize } })
        .then((r) => r.data),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/sources/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sources"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-sources"] });
      addToast("success", "Источник удален");
      setDeleteId(null);
    },
    onError: () => {
      addToast("error", "Не удалось удалить источник");
    },
  });

  const columns = [
    { key: "name", header: "Название" },
    {
      key: "description",
      header: "Описание",
      render: (s: Source) => s.description?.trim() || "—",
    },
    { key: "host", header: "Хост" },
    { key: "database", header: "База данных" },
    {
      key: "connection_status",
      header: "Статус",
      render: (s: Source) => <ConnectionStatus status={s.connection_status} />,
    },
    {
      key: "actions",
      header: "Действия",
      render: (s: Source) => (
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            className="px-2 py-1 text-xs"
            onClick={(e) => {
              e.stopPropagation();
              navigate(`/sources/${s.id}/edit`);
            }}
          >
            Изменить
          </Button>
          <Button
            variant="danger"
            className="px-2 py-1 text-xs"
            onClick={(e) => {
              e.stopPropagation();
              setDeleteId(s.id);
            }}
          >
            Удалить
          </Button>
        </div>
      ),
    },
  ];

  const normalizedSearch = search.trim().toLowerCase();
  const filteredSources = sources.filter((source) => {
    if (!normalizedSearch) return true;
    return (
      source.name.toLowerCase().includes(normalizedSearch) ||
      (source.description || "").toLowerCase().includes(normalizedSearch) ||
      source.host.toLowerCase().includes(normalizedSearch) ||
      source.database.toLowerCase().includes(normalizedSearch)
    );
  });

  if (isLoading) return <div>Загрузка...</div>;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Источники</h1>
        <Button onClick={() => navigate("/sources/new")}>Добавить источник</Button>
      </div>
      <div className="mb-4">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Поиск по названию, описанию, хосту или БД"
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:ring-2 focus:ring-cyan-500/70 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
      </div>

      <Table
        columns={columns}
        data={filteredSources}
        onRowClick={(s) => navigate(`/sources/${s.id}/edit`)}
        emptyMessage={normalizedSearch ? "Ничего не найдено" : "Источники еще не добавлены"}
      />
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
          Назад
        </Button>
        <Button
          variant="secondary"
          onClick={() => setPage((p) => p + 1)}
          disabled={sources.length < pageSize}
        >
          Далее
        </Button>
      </div>

      <Modal
        isOpen={deleteId !== null}
        onClose={() => setDeleteId(null)}
        title="Удаление источника"
      >
        <p className="mb-3 text-sm text-slate-700 dark:text-slate-300">
          Вы уверены, что хотите удалить источник?
        </p>
        <p className="mb-4 text-xs text-amber-700 dark:text-amber-300">
          Внимание: это действие необратимо. Потоки, связанные с этим источником, больше не смогут выполняться.
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setDeleteId(null)}>
            Отмена
          </Button>
          <Button
            variant="danger"
            loading={deleteMutation.isPending}
            onClick={() => deleteId && deleteMutation.mutate(deleteId)}
          >
            Удалить
          </Button>
        </div>
      </Modal>
    </div>
  );
}
