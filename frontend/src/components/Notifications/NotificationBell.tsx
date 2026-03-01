/**
 * Notification bell component (T111).
 */

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import api from "../../services/api";
import { NotificationList } from "./NotificationList";

export function NotificationBell() {
  const [isOpen, setIsOpen] = useState(false);

  const { data } = useQuery({
    queryKey: ["notification-count"],
    queryFn: () => api.get("/notifications/count").then((r) => r.data),
    refetchInterval: 30000,
  });

  const count = data?.unread_count || 0;

  return (
    <div className="relative">
      <button
        className="relative rounded-lg border border-slate-300 bg-white px-2 py-2 text-slate-700 transition hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
        onClick={() => setIsOpen(!isOpen)}
      >
        <span className="text-lg">🔔</span>
        {count > 0 && (
          <span className="absolute right-0 top-0 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-xs text-white">
            {count > 9 ? "9+" : count}
          </span>
        )}
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
          <div className="absolute right-0 z-50 mt-2 w-80">
            <NotificationList onClose={() => setIsOpen(false)} />
          </div>
        </>
      )}
    </div>
  );
}
