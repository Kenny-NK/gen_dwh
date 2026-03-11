/**
 * Toast notification system (T118).
 */

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

interface Toast {
  id: number;
  type: "success" | "error" | "info";
  message: string;
}

interface ToastContextType {
  addToast: (type: Toast["type"], message: string) => void;
}

const ToastContext = createContext<ToastContextType>({ addToast: () => {} });

let toastId = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timersRef = useRef<Map<number, number>>(new Map());

  const removeToast = useCallback((id: number) => {
    const timerId = timersRef.current.get(id);
    if (timerId !== undefined) {
      window.clearTimeout(timerId);
      timersRef.current.delete(id);
    }
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      for (const timerId of timers.values()) {
        window.clearTimeout(timerId);
      }
      timers.clear();
    };
  }, []);

  const addToast = useCallback((type: Toast["type"], message: string) => {
    const id = ++toastId;
    setToasts((prev) => [...prev, { id, type, message }]);
    const timerId = window.setTimeout(() => {
      removeToast(id);
    }, 5000);
    timersRef.current.set(id, timerId);
  }, [removeToast]);

  const typeStyles = {
    success: "bg-green-500",
    error: "bg-red-500",
    info: "bg-blue-500",
  };

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 space-y-2" aria-live="assertive" aria-atomic="true">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="alert"
            className={`flex items-start gap-2 rounded px-4 py-3 text-sm text-white shadow-lg ${typeStyles[toast.type]}`}
          >
            <span className="flex-1">{toast.message}</span>
            <button
              type="button"
              aria-label="Закрыть уведомление"
              className="text-white/90 transition hover:text-white"
              onClick={() => removeToast(toast.id)}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
