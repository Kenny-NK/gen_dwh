/**
 * API client module with auth interceptors (T027).
 */

import axios from "axios";
import type { AxiosError } from "axios";

const api = axios.create({
  baseURL: "/api/v1",
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
  },
});

type ErrorPayload = {
  detail?: string | Array<{ field?: string; message?: string }> | Record<string, unknown>;
  errors?: Array<{ field?: string; message?: string }>;
  error_id?: string;
};

export function extractItems<T>(data: unknown): T[] {
  if (Array.isArray(data)) {
    return data as T[];
  }
  if (typeof data !== "object" || data === null) {
    return [];
  }
  const items = (data as { items?: unknown }).items;
  return Array.isArray(items) ? (items as T[]) : [];
}

export function extractListResponse<T>(data: unknown): { items: T[]; total: number | null } {
  if (Array.isArray(data)) {
    return {
      items: data as T[],
      total: data.length,
    };
  }

  if (typeof data !== "object" || data === null) {
    return {
      items: [],
      total: null,
    };
  }

  const items = extractItems<T>(data);
  const rawTotal = (data as { total?: unknown }).total;
  return {
    items,
    total: typeof rawTotal === "number" && Number.isFinite(rawTotal) ? rawTotal : null,
  };
}

// Response interceptor - handle 401
api.interceptors.response.use(
  (response) => response,
  (error) => {
    return Promise.reject(error);
  }
);

export function extractApiErrorMessage(error: unknown, fallback: string): string {
  const axiosError = error as AxiosError<ErrorPayload>;
  const status = axiosError.response?.status;
  const data = axiosError.response?.data;

  if (typeof data?.detail === "string" && data.detail.trim().length > 0) {
    return data.error_id ? `${data.detail} (код: ${data.error_id})` : data.detail;
  }

  if (Array.isArray(data?.errors) && data.errors.length > 0) {
    const first = data.errors[0];
    if (first.message) {
      return first.field ? `${first.field}: ${first.message}` : first.message;
    }
  }

  if (status === 401) {
    return "Сессия истекла. Авторизуйтесь повторно.";
  }
  if (status === 429) {
    return "Слишком много запросов. Подождите несколько секунд и повторите.";
  }
  if (status === 500) {
    return "Внутренняя ошибка сервера. Повторите попытку чуть позже.";
  }

  return fallback;
}

export default api;
