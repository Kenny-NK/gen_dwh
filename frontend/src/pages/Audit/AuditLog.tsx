import React from "react";

import { Button } from "../../components/common/Button";
import { Input } from "../../components/common/Input";
import { Modal } from "../../components/common/Modal";
import { Table } from "../../components/common/Table";
import { useListWithPagination } from "../../hooks/useListWithPagination";
import { formatDateTime } from "../../utils/formatDate";

type AuditEvent = {
  id: string;
  user_email: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  changes: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
};

function stringifyChanges(changes: Record<string, unknown> | null): string {
  if (!changes || Object.keys(changes).length === 0) {
    return "—";
  }
  return Object.entries(changes)
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${typeof value === "object" ? JSON.stringify(value) : String(value)}`)
    .join(" | ");
}

export default function AuditLog() {
  const [userEmail, setUserEmail] = React.useState("");
  const [action, setAction] = React.useState("");
  const [entityType, setEntityType] = React.useState("");
  const [dateFrom, setDateFrom] = React.useState("");
  const [dateTo, setDateTo] = React.useState("");
  const [selectedEvent, setSelectedEvent] = React.useState<AuditEvent | null>(null);
  const pageSize = 20;

  const params = React.useMemo(
    () => ({
      user_email: userEmail || undefined,
      action: action || undefined,
      entity_type: entityType || undefined,
      date_from: dateFrom ? new Date(`${dateFrom}T00:00:00`).toISOString() : undefined,
      date_to: dateTo ? new Date(`${dateTo}T23:59:59`).toISOString() : undefined,
    }),
    [action, dateFrom, dateTo, entityType, userEmail]
  );

  const {
    items: events,
    total,
    totalPages,
    hasNextPage,
    isLoading,
    isFetching,
    page,
    setPage,
    refetch,
  } = useListWithPagination<AuditEvent>({
    queryKey: ["audit"],
    endpoint: "/audit",
    pageSize,
    params,
    resetPageDeps: [userEmail, action, entityType, dateFrom, dateTo],
  });

  const safeTotal = total ?? events.length;
  const safeTotalPages = totalPages ?? Math.max(1, page);
  const uniqueUsers = new Set(events.map((event) => event.user_email).filter(Boolean)).size;
  const uniqueActions = new Set(events.map((event) => event.action)).size;

  const columns = [
    {
      key: "created_at",
      header: "Дата",
      render: (event: AuditEvent) => (
        <div>
          <div>{formatDateTime(event.created_at)}</div>
          <div className="text-xs font-normal text-slate-500 dark:text-slate-400">{event.id}</div>
        </div>
      ),
    },
    {
      key: "user_email",
      header: "Пользователь",
      render: (event: AuditEvent) => event.user_email || "Системное действие",
    },
    { key: "action", header: "Действие" },
    { key: "entity_type", header: "Сущность" },
    {
      key: "entity_id",
      header: "Entity ID",
      render: (event: AuditEvent) => event.entity_id || "—",
    },
    {
      key: "changes",
      header: "Изменения",
      render: (event: AuditEvent) => (
        <span className="text-xs font-normal text-slate-600 dark:text-slate-300">
          {stringifyChanges(event.changes)}
        </span>
      ),
    },
    {
      key: "ip_address",
      header: "IP",
      render: (event: AuditEvent) => event.ip_address || "—",
    },
    {
      key: "details",
      header: "Детали",
      render: (event: AuditEvent) => (
        <Button
          size="sm"
          variant="secondary"
          onClick={(clickEvent) => {
            clickEvent.stopPropagation();
            setSelectedEvent(event);
          }}
        >
          Открыть
        </Button>
      ),
    },
  ];

  const resetFilters = () => {
    setUserEmail("");
    setAction("");
    setEntityType("");
    setDateFrom("");
    setDateTo("");
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Аудит</h1>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
          Журнал действий пользователей по текущему workspace с фильтрами по пользователю, действию и сущности.
        </p>
      </div>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="app-card p-4">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
            Всего событий
          </div>
          <div className="mt-3 text-3xl font-semibold text-slate-900 dark:text-slate-100">{safeTotal}</div>
          <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">По текущему фильтру</div>
        </div>
        <div className="app-card p-4">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
            Действия
          </div>
          <div className="mt-3 text-3xl font-semibold text-slate-900 dark:text-slate-100">{uniqueActions}</div>
          <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">Разных типов на странице</div>
        </div>
        <div className="app-card p-4">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
            Пользователи
          </div>
          <div className="mt-3 text-3xl font-semibold text-slate-900 dark:text-slate-100">{uniqueUsers}</div>
          <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">Уникальных на странице</div>
        </div>
        <div className="app-card p-4">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
            Состояние
          </div>
          <div className="mt-3 text-sm font-medium text-slate-900 dark:text-slate-100">
            {isFetching ? "Обновление журнала..." : "Данные актуальны"}
          </div>
          <Button className="mt-3 w-full" variant="secondary" onClick={() => void refetch()}>
            Обновить
          </Button>
        </div>
      </section>

      <section className="app-card p-5">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <Input
            label="Пользователь"
            value={userEmail}
            onChange={(event) => {
              setUserEmail(event.target.value);
              setPage(1);
            }}
            placeholder="user@example.com"
          />
          <Input
            label="Действие"
            value={action}
            onChange={(event) => {
              setAction(event.target.value);
              setPage(1);
            }}
            placeholder="delete, update, run"
          />
          <Input
            label="Сущность"
            value={entityType}
            onChange={(event) => {
              setEntityType(event.target.value);
              setPage(1);
            }}
            placeholder="flow, source, run"
          />
          <Input
            label="Дата с"
            type="date"
            value={dateFrom}
            onChange={(event) => {
              setDateFrom(event.target.value);
              setPage(1);
            }}
          />
          <Input
            label="Дата по"
            type="date"
            value={dateTo}
            onChange={(event) => {
              setDateTo(event.target.value);
              setPage(1);
            }}
          />
        </div>
        <div className="mt-4 flex flex-wrap gap-3">
          <Button variant="secondary" onClick={resetFilters}>
            Сбросить фильтры
          </Button>
          <Button variant="secondary" onClick={() => void refetch()}>
            Применить / обновить
          </Button>
        </div>
      </section>

      <section className="space-y-4">
        {isLoading ? (
          <div>Загрузка...</div>
        ) : (
          <>
            <Table
              columns={columns}
              data={events}
              emptyMessage="Событий аудита по текущему фильтру не найдено"
            />
            <div className="flex items-center justify-between text-sm text-slate-500 dark:text-slate-400">
              <span>
                Всего событий: {safeTotal} • Страница {page} из {safeTotalPages}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                  disabled={page === 1}
                >
                  Назад
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => setPage((current) => current + 1)}
                  disabled={!hasNextPage}
                >
                  Далее
                </Button>
              </div>
            </div>
          </>
        )}
      </section>

      <Modal
        isOpen={selectedEvent !== null}
        onClose={() => setSelectedEvent(null)}
        title="Детали события аудита"
      >
        {selectedEvent && (
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-800/70">
                <div className="text-xs uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">Действие</div>
                <div className="mt-1 font-medium text-slate-900 dark:text-slate-100">{selectedEvent.action}</div>
              </div>
              <div className="rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-800/70">
                <div className="text-xs uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">Сущность</div>
                <div className="mt-1 font-medium text-slate-900 dark:text-slate-100">{selectedEvent.entity_type}</div>
              </div>
              <div className="rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-800/70">
                <div className="text-xs uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">Пользователь</div>
                <div className="mt-1 font-medium text-slate-900 dark:text-slate-100">{selectedEvent.user_email || "Системное действие"}</div>
              </div>
              <div className="rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-800/70">
                <div className="text-xs uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">Дата</div>
                <div className="mt-1 font-medium text-slate-900 dark:text-slate-100">
                  {formatDateTime(selectedEvent.created_at)}
                </div>
              </div>
            </div>
            <div>
              <div className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">Изменения</div>
              <pre className="max-h-[26rem] overflow-auto rounded-xl bg-slate-950 p-4 text-xs leading-6 text-slate-100">
                {JSON.stringify(selectedEvent.changes ?? {}, null, 2)}
              </pre>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
