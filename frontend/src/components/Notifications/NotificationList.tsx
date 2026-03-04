/**
 * Notification dropdown/list (T112).
 */

import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import api from "../../services/api";

interface NotificationListProps {
  onClose: () => void;
}

interface NotificationItem {
  id: string;
  type: string;
  title: string;
  message: string;
  is_read: boolean;
  created_at: string;
}

const typeColors: Record<string, string> = {
  success: "border-l-green-500",
  error: "border-l-red-500",
  warning: "border-l-yellow-500",
  info: "border-l-blue-500",
};

export function NotificationList({ onClose }: NotificationListProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [page, setPage] = React.useState(1);
  const pageSize = 10;

  const { data: notifications = [] } = useQuery<NotificationItem[]>({
    queryKey: ["notifications", page],
    queryFn: () =>
      api
        .get("/notifications", { params: { limit: pageSize, offset: (page - 1) * pageSize } })
        .then((r) => r.data),
  });

  const markAllRead = useMutation({
    mutationFn: () => api.post("/notifications/read-all"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
      queryClient.invalidateQueries({ queryKey: ["notification-count"] });
    },
  });

  return (
    <div className="max-h-96 overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-700">
        <h3 className="font-semibold text-slate-900 dark:text-slate-100">{t("notifications")}</h3>
        <button
          className="text-xs text-cyan-600 transition hover:underline dark:text-cyan-400"
          onClick={() => markAllRead.mutate()}
        >
          {t("read_all")}
        </button>
      </div>
      <div className="divide-y divide-slate-200 dark:divide-slate-700">
        {notifications.map((n) => (
          <div
            key={n.id}
            className={`border-l-4 px-4 py-3 ${typeColors[n.type] || ""} ${
              !n.is_read ? "bg-cyan-50 dark:bg-cyan-950/20" : ""
            }`}
          >
            <div className="text-sm font-medium text-slate-900 dark:text-slate-100">{n.title}</div>
            <div className="text-xs text-slate-500 dark:text-slate-400">{n.message}</div>
            <div className="mt-1 text-xs text-slate-400 dark:text-slate-500">
              {new Date(n.created_at).toLocaleString()}
            </div>
          </div>
        ))}
        {notifications.length === 0 && (
          <div className="px-4 py-8 text-center text-sm text-slate-500 dark:text-slate-400">
            {t("no_notifications")}
          </div>
        )}
      </div>
      <div className="flex items-center justify-between border-t border-slate-200 px-4 py-2 dark:border-slate-700">
        <div className="flex gap-2">
          <button
            className="text-xs text-slate-500 transition hover:text-slate-700 disabled:opacity-50 dark:text-slate-400 dark:hover:text-slate-200"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
          >
            Назад
          </button>
          <button
            className="text-xs text-slate-500 transition hover:text-slate-700 disabled:opacity-50 dark:text-slate-400 dark:hover:text-slate-200"
            onClick={() => setPage((p) => p + 1)}
            disabled={notifications.length < pageSize}
          >
            Далее
          </button>
        </div>
        <button
          className="text-xs text-slate-500 transition hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
          onClick={onClose}
        >
          {t("close")}
        </button>
      </div>
    </div>
  );
}
